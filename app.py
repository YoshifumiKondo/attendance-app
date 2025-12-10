import streamlit as st
import pandas as pd
import datetime
import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import base64
from io import BytesIO

# --- 設定 ---
st.set_page_config(
    page_title="勤怠管理アプリ",
    page_icon="⏰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 定数
WORK_HOURS_PER_DAY = 8
OVERTIME_RATE = 1.25

# --- データベース接続 (Firestore) ---
if not firebase_admin._apps:
    if "firebase" in st.secrets:
        cred_info = dict(st.secrets["firebase"])
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    else:
        st.error("【重要】Firebase認証情報が設定されていません。Streamlit Secretsを設定してください。")
        st.stop()

db = firestore.client()

# --- ユーティリティ ---
import hashlib
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_time_str():
    return datetime.datetime.now().strftime("%H:%M")

def get_today_str():
    return datetime.date.today().strftime("%Y-%m-%d")

# --- データベース操作関数 ---
def get_employee(name):
    docs = db.collection('employees').where('name', '==', name).stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None

def get_employee_by_id(doc_id):
    doc = db.collection('employees').document(doc_id).get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id
        return data
    return None

def get_all_employees():
    docs = db.collection('employees').stream()
    employees = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        employees.append(data)
    return employees

def get_admin(username):
    docs = db.collection('admins').where('username', '==', username).stream()
    for doc in docs:
        return doc.to_dict()
    return None

def get_attendance(employee_id, date_str):
    docs = db.collection('attendance')\
             .where('employee_id', '==', employee_id)\
             .where('date', '==', date_str)\
             .stream()
    for doc in docs:
        data = doc.to_dict()
        data['doc_id'] = doc.id
        return data
    return None

# --- UIコンポーネント（ポップなデザイン設定） ---
def style_setup():
    st.markdown("""
    <style>
        /* Google Fonts: M PLUS Rounded 1c (丸ゴシック) をインポート */
        @import url('https://fonts.googleapis.com/css2?family=M+PLUS+Rounded+1c:wght@400;700&display=swap');

        /* 全体のフォント適用 */
        html, body, [class*="css"] {
            font-family: 'M PLUS Rounded 1c', sans-serif;
        }

        /* タイトルの装飾 */
        h1 {
            color: #FF8BA7; /* ポップなピンク */
            text-shadow: 2px 2px 0px #FFF0F5;
        }
        h2, h3 {
            color: #555;
        }

        /* ボタンの共通スタイル */
        .stButton>button {
            width: 100%;
            height: 3.5em;
            font-size: 1.3em;
            font-weight: bold;
            border-radius: 50px; /* 丸っこく */
            border: none;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); /* 影をつける */
            transition: all 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-2px); /* ホバーで少し浮く */
            box-shadow: 0 6px 8px rgba(0,0,0,0.15);
        }
        .stButton>button:active {
            transform: translateY(1px); /* 押すと沈む */
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        /* カラムごとのボタン色分け (Streamlitの構造に依存したハック) */
        
        /* 1番目のカラム（出勤・ログインなど）: ミントグリーン */
        div[data-testid="column"]:nth-of-type(1) .stButton>button {
            background-color: #A0E7E5; 
            color: #333;
        }
        
        /* 2番目のカラム（退勤など）: サーモンピンク */
        div[data-testid="column"]:nth-of-type(2) .stButton>button {
            background-color: #FFAEBC; 
            color: #333;
        }

        /* 3番目のカラム（休憩開始）: レモンイエロー */
        div[data-testid="column"]:nth-of-type(3) .stButton>button {
            background-color: #FBE7C6; 
            color: #333;
        }

        /* 4番目のカラム（休憩終了）: パステルブルー */
        div[data-testid="column"]:nth-of-type(4) .stButton>button {
            background-color: #B4F8C8; 
            color: #333;
        }

        /* 指標（Metric）のカード化 */
        div[data-testid="stMetric"] {
            background-color: #FFF;
            padding: 15px;
            border-radius: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            text-align: center;
            border: 2px solid #F0F0F0;
        }
        
        /* 入力フォームの角丸 */
        .stTextInput>div>div>input {
            border-radius: 20px;
        }
        .stSelectbox>div>div>div {
            border-radius: 20px;
        }

    </style>
    """, unsafe_allow_html=True)

# --- 画面: 認証 ---
def login_screen():
    st.title("勤怠管理アプリ 🍩")
    
    admins = db.collection('admins').limit(1).stream()
    if not list(admins):
        st.warning("管理者が登録されていません。初期アカウントを作成します。")
        if st.button("初期管理者作成"):
            hashed = hash_password("password")
            db.collection('admins').add({
                "username": "admin",
                "password": hashed
            })
            st.success("作成しました。")
            time.sleep(2)
            st.rerun()

    tab1, tab2 = st.tabs(["🐣 スタッフ", "🔧 管理者"])
    
    with tab1:
        st.header("さあ、はじめましょう！")
        employees = get_all_employees()
        if not employees:
            st.info("スタッフが登録されていません。")
        else:
            emp_names = [e['name'] for e in employees]
            selected_name = st.selectbox("お名前を選んでください", emp_names)
            pin = st.text_input("暗証番号 (4桁)", type="password", key="staff_pin", max_chars=4)
            
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                if st.button("スタート ▶︎", key="staff_login_btn"):
                    emp_data = get_employee(selected_name)
                    if emp_data and emp_data.get('pin') == pin:
                        st.session_state['logged_in'] = True
                        st.session_state['user_role'] = 'staff'
                        st.session_state['user_id'] = emp_data['id']
                        st.session_state['user_name'] = selected_name
                        st.rerun()
                    else:
                        st.error("暗証番号が違います🥺")

    with tab2:
        st.header("管理者ログイン")
        admin_user = st.text_input("管理者ID")
        admin_pass = st.text_input("パスワード", type="password")
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
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
    st.title(f"お疲れ様です、{st.session_state['user_name']}さん ✨")
    
    today = get_today_str()
    record = get_attendance(st.session_state['user_id'], today)
    
    clock_in = record.get('clock_in') if record else None
    clock_out = record.get('clock_out') if record else None
    break_start = record.get('break_start') if record else None
    break_end = record.get('break_end') if record else None
    doc_id = record.get('doc_id') if record else None

    st.markdown("### 📅 今日のステータス")
    c1, c2 = st.columns(2)
    c1.metric("出勤時刻", clock_in if clock_in else "--:--")
    c2.metric("退勤時刻", clock_out if clock_out else "--:--")

    st.write("")

    photo = st.camera_input("認証用写真撮影", label_visibility="collapsed")
    photo_b64 = None
    if photo:
        photo_b64 = base64.b64encode(photo.getvalue()).decode()

    st.write("")

    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        if st.button("☀️ 出勤"):
            if not photo_b64:
                st.warning("写真を撮影してください📸")
            elif clock_in:
                st.warning("すでに出勤しています")
            else:
                db.collection('attendance').add({
                    'employee_id': st.session_state['user_id'],
                    'date': today,
                    'clock_in': get_current_time_str(),
                    'photo': photo_b64,
                    'created_at': firestore.SERVER_TIMESTAMP
                })
                st.success("おはようございます！今日も頑張りましょう！🌈")
                time.sleep(2)
                st.rerun()

    with col2:
        if st.button("🌙 退勤"):
            if not clock_in:
                st.warning("まだ出勤していません")
            elif clock_out:
                st.warning("すでに退勤しています")
            else:
                db.collection('attendance').document(doc_id).update({
                    'clock_out': get_current_time_str()
                })
                st.success("お疲れ様でした！ゆっくり休んでください🍵")
                time.sleep(2)
                st.rerun()
    
    with col3:
        if st.button("☕️ 休憩"):
            if doc_id and not break_start:
                db.collection('attendance').document(doc_id).update({
                    'break_start': get_current_time_str()
                })
                st.rerun()
            else:
                st.warning("操作できません")

    with col4:
        if st.button("💪 再開"):
            if doc_id and break_start and not break_end:
                db.collection('attendance').document(doc_id).update({
                    'break_end': get_current_time_str()
                })
                st.rerun()
            else:
                st.warning("操作できません")

    st.divider()

    with st.expander("💰 今月の概算給与"):
        emp = get_employee_by_id(st.session_state['user_id'])
        current_month = datetime.datetime.now().strftime("%Y-%m")
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
                work_hours += max(0, hours - 1)
        
        est_pay = 0
        if emp['salary_type'] == '月給':
            est_pay = emp['salary']
        else:
            est_pay = int(work_hours * emp['salary'])
            
        if st.checkbox("金額を表示する"):
            st.metric("概算給与", f"{est_pay:,} 円")
        else:
            st.metric("概算給与", "***** 円")

# --- 画面: 管理者機能 ---
def admin_dashboard():
    st.title("管理者ダッシュボード 🛠️")
    menu = st.sidebar.radio("メニュー", ["👥 スタッフ管理", "✏️ 勤怠修正", "📊 勤怠集計", "⚙️ システム設定"])

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
            st.dataframe(df[['name', 'employee_type', 'salary_type', 'id']])
            
            # --- 従業員マスタのエクスポート機能 ---
            output_emp = BytesIO()
            with pd.ExcelWriter(output_emp, engine='openpyxl') as writer:
                # 必要なカラムのみを選択して出力（idやpinは管理用として出力）
                export_cols = ['id', 'name', 'birth_date', 'employee_type', 'salary_type', 'salary', 'transportation', 'pin']
                valid_cols = [c for c in export_cols if c in df.columns]
                df[valid_cols].to_excel(writer, sheet_name='従業員マスタ', index=False)
            output_emp.seek(0)
            st.download_button("従業員マスタ Excel出力", data=output_emp, file_name="employee_master.xlsx")
            # ------------------------------------

            del_id = st.selectbox("削除対象ID", [e['id'] for e in emps])
            if st.button("選択したスタッフを削除"):
                db.collection('employees').document(del_id).delete()
                st.warning("削除しました")
                time.sleep(1)
                st.rerun()

    elif menu == "✏️ 勤怠修正":
        st.subheader("勤怠データの修正・追加")
        st.info("スタッフと日付を選択して、打刻時間を修正できます。")

        emps = get_all_employees()
        if emps:
            c1, c2 = st.columns(2)
            selected_emp_id = c1.selectbox("スタッフ選択", [e['id'] for e in emps], format_func=lambda x: next(e['name'] for e in emps if e['id'] == x))
            selected_date = c2.date_input("日付選択", value=datetime.date.today())
            date_str = str(selected_date)

            record = get_attendance(selected_emp_id, date_str)
            
            def_in = datetime.time(9, 0)
            def_out = datetime.time(18, 0)
            def_b_start = None
            def_b_end = None
            doc_id = None
            
            if record:
                st.write("📝 データが見つかりました。修正します。")
                doc_id = record['doc_id']
                if record.get('clock_in'):
                    def_in = datetime.datetime.strptime(record['clock_in'], "%H:%M").time()
                if record.get('clock_out'):
                    def_out = datetime.datetime.strptime(record['clock_out'], "%H:%M").time()
                if record.get('break_start'):
                    def_b_start = datetime.datetime.strptime(record['break_start'], "%H:%M").time()
                if record.get('break_end'):
                    def_b_end = datetime.datetime.strptime(record['break_end'], "%H:%M").time()
            else:
                st.warning("⚠️ この日のデータはありません。新規作成しますか？")

            with st.form("edit_attendance"):
                tc1, tc2 = st.columns(2)
                new_in = tc1.time_input("出勤時間", value=def_in)
                new_out = tc2.time_input("退勤時間", value=def_out)
                
                tc3, tc4 = st.columns(2)
                new_b_start = tc3.time_input("休憩開始", value=def_b_start)
                new_b_end = tc4.time_input("休憩終了", value=def_b_end)
                
                if st.form_submit_button("保存する"):
                    data = {
                        'clock_in': new_in.strftime("%H:%M"),
                        'clock_out': new_out.strftime("%H:%M"),
                        'break_start': new_b_start.strftime("%H:%M") if new_b_start else None,
                        'break_end': new_b_end.strftime("%H:%M") if new_b_end else None,
                        'date': date_str,
                        'employee_id': selected_emp_id
                    }
                    if doc_id:
                        db.collection('attendance').document(doc_id).update(data)
                        st.success("データを更新しました！")
                    else:
                        data['created_at'] = firestore.SERVER_TIMESTAMP
                        db.collection('attendance').add(data)
                        st.success("データを新規作成しました！")
                    time.sleep(1)
                    st.rerun()

    elif menu == "📊 勤怠集計":
        st.subheader("データ出力")
        d1, d2 = st.columns(2)
        start_d = d1.date_input("開始", value=datetime.date.today().replace(day=1))
        end_d = d2.date_input("終了", value=datetime.date.today())
        
        if st.button("集計実行"):
            all_logs = db.collection('attendance').stream()
            data_list = []
            emp_map = {e['id']: e for e in get_all_employees()}
            
            for doc in all_logs:
                d = doc.to_dict()
                log_date = datetime.datetime.strptime(d['date'], "%Y-%m-%d").date()
                if start_d <= log_date <= end_d:
                    emp = emp_map.get(d['employee_id'])
                    if emp:
                        # 日付を年、月、日に分割
                        ymd = d['date'].split('-')
                        data_list.append({
                            '名前': emp['name'],
                            '年': int(ymd[0]),
                            '月': int(ymd[1]),
                            '日': int(ymd[2]),
                            '出勤': d.get('clock_in'),
                            '退勤': d.get('clock_out'),
                            '休憩開始': d.get('break_start'),
                            '休憩終了': d.get('break_end'),
                            '給与形態': emp['salary_type']
                            # 時給・月給は出力しない
                        })
            
            if not data_list:
                st.warning("対象期間のデータがありません")
            else:
                # カラム順序の指定
                cols = ['名前', '年', '月', '日', '出勤', '退勤', '休憩開始', '休憩終了', '給与形態']
                df_res = pd.DataFrame(data_list, columns=cols)
                
                st.dataframe(df_res)
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_res.to_excel(writer, sheet_name='勤怠', index=False)
                output.seek(0)
                st.download_button("Excelダウンロード", data=output, file_name="attendance.xlsx")

    elif menu == "⚙️ システム設定":
        st.info("Firestoreを使用しているため、データはクラウドに永続化されています。")
        new_p = st.text_input("管理者パスワード変更", type="password")
        if st.button("変更"):
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
