import streamlit as st
import pandas as pd
import datetime
import calendar
import hashlib
import base64
from io import BytesIO
import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json

# --- 設定 ---
st.set_page_config(
    page_title="勤怠管理アプリ(本番版)",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 定数
WORK_HOURS_PER_DAY = 8
OVERTIME_RATE = 1.25

# --- データベース接続 (Firestore) ---
# シングルトンパターンでFirebase初期化（多重初期化防止）
if not firebase_admin._apps:
    # Streamlit CloudのSecretsから認証情報を読み込む想定
    # ローカル開発時でも secrets.toml があれば動作します
    if "firebase" in st.secrets:
        cred_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    else:
        st.error("【重要】Firebase認証情報が設定されていません。Streamlit Secretsを設定してください。")
        st.stop()

db = firestore.client()

# --- ユーティリティ ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_time_str():
    return datetime.datetime.now().strftime("%H:%M")

def get_today_str():
    return datetime.date.today().strftime("%Y-%m-%d")

# --- データベース操作関数 ---

def get_employee(name):
    """名前から従業員ドキュメントを取得"""
    docs = db.collection('employees').where('name', '==', name).stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id  # ドキュメントIDを含める
        return data
    return None

def get_employee_by_id(doc_id):
    """IDから従業員情報を取得"""
    doc = db.collection('employees').document(doc_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None

def get_all_employees():
    """全従業員を取得"""
    docs = db.collection('employees').stream()
    employees = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        employees.append(data)
    return employees

def get_admin(username):
    """管理者を取得"""
    docs = db.collection('admins').where('username', '==', username).stream()
    for doc in docs:
        return doc.to_dict()
    return None

def get_today_attendance(employee_id, date_str):
    """特定の従業員の指定日の勤怠を取得"""
    docs = db.collection('attendance')\
             .where('employee_id', '==', employee_id)\
             .where('date', '==', date_str)\
             .stream()
    for doc in docs:
        data = doc.to_dict()
        data['doc_id'] = doc.id
        return data
    return None

# --- UIコンポーネント ---
def style_setup():
    st.markdown("""
    <style>
        .stButton>button {
            width: 100%;
            height: 3em;
            font-size: 1.2em;
            font-weight: bold;
            border-radius: 10px;
        }
        /* 出勤ボタン */
        div[data-testid="column"]:nth-of-type(1) .stButton>button {
            background-color: #E2F0CB; 
            color: #4A4A4A;
        }
        /* 退勤ボタン */
        div[data-testid="column"]:nth-of-type(2) .stButton>button {
            background-color: #FFDAC1; 
            color: #4A4A4A;
        }
    </style>
    """, unsafe_allow_html=True)

# --- 画面: 認証 ---
def login_screen():
    st.title("勤怠管理アプリ (本番環境) 🏢")
    
    # 初期管理者チェック（Firestoreに管理者がいない場合作成）
    admins = db.collection('admins').limit(1).stream()
    if not list(admins):
        st.warning("管理者が登録されていません。初期アカウントを作成します。")
        if st.button("初期管理者作成"):
            hashed = hash_password("password")
            db.collection('admins').add({
                "username": "admin",
                "password": hashed
            })
            st.success("作成しました。ID: admin / Pass: password でログインしてください。")
            time.sleep(2)
            st.rerun()

    tab1, tab2 = st.tabs(["スタッフ", "管理者"])
    
    with tab1:
        st.header("はじめる")
        employees = get_all_employees()
        if not employees:
            st.info("スタッフが登録されていません。")
        else:
            emp_names = [e['name'] for e in employees]
            selected_name = st.selectbox("お名前を選んでください", emp_names)
            
            pin = st.text_input("暗証番号 (4桁)", type="password", key="staff_pin", max_chars=4)
            
            if st.button("スタート", key="staff_login_btn"):
                emp_data = get_employee(selected_name)
                if emp_data and emp_data.get('pin') == pin:
                    st.session_state['logged_in'] = True
                    st.session_state['user_role'] = 'staff'
                    st.session_state['user_id'] = emp_data['id']
                    st.session_state['user_name'] = selected_name
                    st.rerun()
                else:
                    st.error("暗証番号が違います")

    with tab2:
        st.header("管理者ログイン")
        admin_user = st.text_input("管理者ID")
        admin_pass = st.text_input("パスワード", type="password")
        
        if st.button("ログイン", key="admin_login_btn"):
            admin_data = get_admin(admin_user)
            if admin_data and admin_data['password'] == hash_password(admin_pass):
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = 'admin'
                st.session_state['user_name'] = admin_user
                st.rerun()
            else:
                st.error("IDまたはパスワードが違います")

# --- 画面: スタッフ機能 ---
def staff_dashboard():
    st.title(f"お疲れ様です、{st.session_state['user_name']}さん 🌿")
    
    today = get_today_str()
    record = get_today_attendance(st.session_state['user_id'], today)
    
    clock_in = record.get('clock_in') if record else None
    clock_out = record.get('clock_out') if record else None
    break_start = record.get('break_start') if record else None
    break_end = record.get('break_end') if record else None
    doc_id = record.get('doc_id') if record else None

    # ステータス表示
    c1, c2 = st.columns(2)
    c1.metric("出勤時刻", clock_in if clock_in else "--:--")
    c2.metric("退勤時刻", clock_out if clock_out else "--:--")

    st.divider()

    # カメラとボタン
    photo = st.camera_input("認証用写真撮影", label_visibility="collapsed")
    photo_b64 = None
    if photo:
        photo_b64 = base64.b64encode(photo.getvalue()).decode()

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        if st.button("出勤"):
            if not photo_b64:
                st.warning("写真を撮影してください📸")
            elif clock_in:
                st.warning("すでに出勤しています")
            else:
                # 新規ドキュメント作成
                db.collection('attendance').add({
                    'employee_id': st.session_state['user_id'],
                    'date': today,
                    'clock_in': get_current_time_str(),
                    'photo': photo_b64,
                    'created_at': firestore.SERVER_TIMESTAMP
                })
                st.success("おはようございます！☀️")
                time.sleep(1)
                st.rerun()

    with col2:
        if st.button("退勤"):
            if not clock_in:
                st.warning("まだ出勤していません")
            elif clock_out:
                st.warning("すでに退勤しています")
            else:
                db.collection('attendance').document(doc_id).update({
                    'clock_out': get_current_time_str()
                })
                st.success("お疲れ様でした！🌙")
                time.sleep(1)
                st.rerun()
    
    with col3:
        if st.button("休憩開始"):
            if doc_id and not break_start:
                db.collection('attendance').document(doc_id).update({
                    'break_start': get_current_time_str()
                })
                st.rerun()
            else:
                st.warning("操作できません")

    with col4:
        if st.button("休憩終了"):
            if doc_id and break_start and not break_end:
                db.collection('attendance').document(doc_id).update({
                    'break_end': get_current_time_str()
                })
                st.rerun()
            else:
                st.warning("操作できません")

    # 簡易給与概算（スタッフ向け）
    with st.expander("今月の概算給与"):
        emp = get_employee_by_id(st.session_state['user_id'])
        current_month = datetime.datetime.now().strftime("%Y-%m")
        
        # クエリ: 今月のデータを取得 (文字列比較)
        # Note: 文字列日付の範囲検索は簡易実装です。厳密にはTimestamp型推奨ですが、
        # 仕様のシンプルさを優先してYYYY-MM-DD文字列でフィルタします。
        start_m = current_month + "-01"
        end_m = current_month + "-31"
        
        logs = db.collection('attendance')\
                 .where('employee_id', '==', st.session_state['user_id'])\
                 .where('date', '>=', start_m)\
                 .where('date', '<=', end_m)\
                 .stream()
        
        work_hours = 0
        for log in logs:
            d = log.to_dict()
            if d.get('clock_in') and d.get('clock_out'):
                t1 = datetime.datetime.strptime(d['clock_in'], "%H:%M")
                t2 = datetime.datetime.strptime(d['clock_out'], "%H:%M")
                hours = (t2 - t1).seconds / 3600
                work_hours += max(0, hours - 1) # 休憩1時間控除仮定
        
        est_pay = 0
        if emp['salary_type'] == '月給':
            est_pay = emp['salary']
        else:
            est_pay = int(work_hours * emp['salary'])
            
        if st.checkbox("金額を表示"):
            st.metric("概算給与", f"{est_pay:,} 円")
        else:
            st.metric("概算給与", "***** 円")


# --- 画面: 管理者機能 ---
def admin_dashboard():
    st.title("管理者ダッシュボード 🛠️")
    menu = st.sidebar.radio("メニュー", ["👥 スタッフ管理", "📊 勤怠集計", "⚙️ システム設定"])

    if menu == "👥 スタッフ管理":
        st.subheader("スタッフ登録")
        with st.form("add_emp"):
            c1, c2 = st.columns(2)
            name = c1.text_input("氏名")
            birth = c2.date_input("生年月日", min_value=datetime.date(1960, 1, 1))
            c3, c4 = st.columns(2)
            e_type = c3.selectbox("雇用形態", ["社員", "AP"])
            s_type = c4.selectbox("給与形態", ["月給", "時給"])
            c5, c6 = st.columns(2)
            salary = c5.number_input("給与額", min_value=0)
            trans = c6.number_input("交通費", min_value=0)
            pin = st.text_input("暗証番号 (4桁)", max_chars=4)
            
            if st.form_submit_button("登録"):
                db.collection('employees').add({
                    'name': name,
                    'birth_date': str(birth),
                    'employee_type': e_type,
                    'salary_type': s_type,
                    'salary': salary,
                    'transportation': trans,
                    'pin': pin,
                    'created_at': firestore.SERVER_TIMESTAMP
                })
                st.success("登録しました")
                time.sleep(1)
                st.rerun()

        st.subheader("登録済みスタッフ")
        emps = get_all_employees()
        if emps:
            df = pd.DataFrame(emps)
            # 表示用にカラム整理
            st.dataframe(df[['name', 'employee_type', 'salary_type', 'id']])
            
            # 削除機能
            del_id = st.selectbox("削除対象ID", [e['id'] for e in emps])
            if st.button("選択したスタッフを削除"):
                db.collection('employees').document(del_id).delete()
                st.warning("削除しました")
                time.sleep(1)
                st.rerun()

    elif menu == "📊 勤怠集計":
        st.subheader("データ出力")
        d1, d2 = st.columns(2)
        start_d = d1.date_input("開始", value=datetime.date.today().replace(day=1))
        end_d = d2.date_input("終了", value=datetime.date.today())
        
        if st.button("集計実行"):
            # 日付範囲でフィルタ
            # 注意: Firestoreで複数のフィールド('date'と'employee_id'等)でフィルタする場合、
            # 複合インデックスが必要になることがあります。
            # 今回はシンプルに全件取得してからPandasで処理する方式が、
            # データ量が少ないうちは最も安定します。
            
            all_logs = db.collection('attendance').stream()
            data_list = []
            
            # 全スタッフマスタ取得
            emp_map = {e['id']: e for e in get_all_employees()}
            
            for doc in all_logs:
                d = doc.to_dict()
                log_date = datetime.datetime.strptime(d['date'], "%Y-%m-%d").date()
                
                if start_d <= log_date <= end_d:
                    emp = emp_map.get(d['employee_id'])
                    if emp:
                        data_list.append({
                            '名前': emp['name'],
                            '日付': d['date'],
                            '出勤': d.get('clock_in'),
                            '退勤': d.get('clock_out'),
                            '給与形態': emp['salary_type'],
                            '時給/月給': emp['salary']
                        })
            
            if not data_list:
                st.warning("対象期間のデータがありません")
            else:
                df_res = pd.DataFrame(data_list)
                st.dataframe(df_res)
                
                # Excel出力
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_res.to_excel(writer, sheet_name='勤怠', index=False)
                output.seek(0)
                
                st.download_button("Excelダウンロード", data=output, file_name="attendance.xlsx")

    elif menu == "⚙️ システム設定":
        st.info("Firestoreを使用しているため、データはクラウドに永続化されています。")
        new_p = st.text_input("管理者パスワード変更", type="password")
        if st.button("変更"):
            # adminドキュメントを探して更新
            docs = db.collection('admins').where('username', '==', 'admin').stream()
            for doc in docs:
                db.collection('admins').document(doc.id).update({
                    'password': hash_password(new_p)
                })
            st.success("変更しました")

# --- メイン実行 ---
def main():
    style_setup()
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if st.session_state['logged_in']:
        with st.sidebar:
            st.write(f"User: {st.session_state.get('user_name')}")
            if st.button("ログアウト"):
                st.session_state.clear()
                st.rerun()

    if not st.session_state['logged_in']:
        login_screen()
    else:
        if st.session_state['user_role'] == 'staff':
            staff_dashboard()
        else:
            admin_dashboard()

if __name__ == "__main__":
    main()
