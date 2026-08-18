import asyncio
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from queue import Queue
from flask_cors import CORS
from myUtils.auth import check_cookie
from flask import Flask, request, jsonify, Response, render_template, send_from_directory
from werkzeug.utils import secure_filename
from conf import BASE_DIR
from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs

active_queues = {}
app = Flask(__name__)

#鍏佽鎵€鏈夋潵婧愯法鍩熻闂?
CORS(app)

# 闄愬埗涓婁紶鏂囦欢澶у皬涓?60MB
app.config['MAX_CONTENT_LENGTH'] = 160 * 1024 * 1024

# 鑾峰彇褰撳墠鐩綍锛堝亣璁?index.html 鍜?assets 鍦ㄨ繖閲岋級
current_dir = os.path.dirname(os.path.abspath(__file__))

# 澶勭悊鎵€鏈夐潤鎬佽祫婧愯姹傦紙鏈潵鎵撳寘鐢級
@app.route('/assets/<filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(current_dir, 'assets'), filename)

# 澶勭悊 favicon.ico 闈欐€佽祫婧愶紙鏈潵鎵撳寘鐢級
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

# 锛堟湭鏉ユ墦鍖呯敤锛?
@app.route('/')
def index():  # put application's code here
    return send_from_directory(current_dir, 'index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400
    try:
        # 淇濆瓨鏂囦欢鍒版寚瀹氫綅缃?
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        safe_name = secure_filename(file.filename)
        if not safe_name:
            return jsonify({"code": 400, "data": None, "msg": "Invalid filename"}), 400
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{safe_name}")
        file.save(filepath)
        return jsonify({"code":200,"msg": "File uploaded successfully", "data": f"{uuid_v1}_{safe_name}"}), 200
    except Exception as e:
        return jsonify({"code":500,"msg": str(e),"data":None}), 500

@app.route('/getFile', methods=['GET'])
def get_file():
    # 鑾峰彇 filename 鍙傛暟
    filename = request.args.get('filename')

    if not filename:
        return jsonify({"code": 400, "msg": "filename is required", "data": None}), 400

    # 闃叉璺緞绌胯秺鏀诲嚮
    if '..' in filename or filename.startswith('/'):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400

    # 鎷兼帴瀹屾暣璺緞
    file_path = str(Path(BASE_DIR, "videoFile"))

    # 杩斿洖鏂囦欢
    return send_from_directory(file_path,filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400

    # 鑾峰彇琛ㄥ崟涓殑鑷畾涔夋枃浠跺悕锛堝彲閫夛級
    custom_filename = request.form.get('filename', None)
    if custom_filename:
        filename = secure_filename(custom_filename + "." + file.filename.split('.')[-1])
    else:
        filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"code": 400, "data": None, "msg": "Invalid filename"}), 400

    try:
        # 鐢熸垚 UUID v1
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")

        # 鏋勯€犳枃浠跺悕鍜岃矾寰?
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{filename}")

        # 淇濆瓨鏂囦欢
        file.save(filepath)

        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO file_records (filename, filesize, file_path)
            VALUES (?, ?, ?)
                                ''', (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024),2), final_filename))
            conn.commit()
            print("鉁?涓婁紶鏂囦欢宸茶褰?)

        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {
                "filename": filename,
                "filepath": final_filename
            }
        }), 200

    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"upload failed: {e}",
            "data": None
        }), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        # 浣跨敤 with 鑷姩绠＄悊鏁版嵁搴撹繛鎺?
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row  # 鍏佽閫氳繃鍒楀悕璁块棶缁撴灉
            cursor = conn.cursor()

            # 鏌ヨ鎵€鏈夎褰?
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            # 灏嗙粨鏋滆浆涓哄瓧鍏稿垪琛紝骞舵彁鍙朥UID
            data = []
            for row in rows:
                row_dict = dict(row)
                # 浠?file_path 涓彁鍙?UUID (鏂囦欢鍚嶇殑绗竴閮ㄥ垎锛屼笅鍒掔嚎鍓?
                if row_dict.get('file_path'):
                    file_path_parts = row_dict['file_path'].split('_', 1)  # 鍙垎鍓茬涓€涓笅鍒掔嚎
                    if len(file_path_parts) > 0:
                        row_dict['uuid'] = file_path_parts[0]  # UUID 閮ㄥ垎
                    else:
                        row_dict['uuid'] = ''
                else:
                    row_dict['uuid'] = ''
                data.append(row_dict)

            return jsonify({
                "code": 200,
                "msg": "success",
                "data": data
            }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("get file failed!"),
            "data": None
        }), 500


@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    """蹇€熻幏鍙栨墍鏈夎处鍙蜂俊鎭紝涓嶈繘琛宑ookie楠岃瘉"""
    try:
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM user_info''')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            print("\n馃搵 褰撳墠鏁版嵁琛ㄥ唴瀹癸紙蹇€熻幏鍙栵級锛?)
            for row in rows:
                print(row)

            return jsonify(
                {
                    "code": 200,
                    "msg": None,
                    "data": rows_list
                }), 200
    except Exception as e:
        print(f"鑾峰彇璐﹀彿鍒楄〃鏃跺嚭閿? {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"鑾峰彇璐﹀彿鍒楄〃澶辫触: {str(e)}",
            "data": None
        }), 500


@app.route("/getValidAccounts",methods=['GET'])
async def getValidAccounts():
    with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM user_info''')
        rows = cursor.fetchall()
        rows_list = [list(row) for row in rows]
        print("\n馃搵 褰撳墠鏁版嵁琛ㄥ唴瀹癸細")
        for row in rows:
            print(row)
        for row in rows_list:
            flag = await check_cookie(row[1],row[2])
            if not flag:
                row[4] = 0
                cursor.execute('''
                UPDATE user_info 
                SET status = ? 
                WHERE id = ?
                ''', (0,row[0]))
                conn.commit()
                print("鉁?鐢ㄦ埛鐘舵€佸凡鏇存柊")
        for row in rows:
            print(row)
        return jsonify(
                        {
                            "code": 200,
                            "msg": None,
                            "data": rows_list
                        }),200

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')

    if not file_id or not file_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing file ID",
            "data": None
        }), 400

    try:
        # 鑾峰彇鏁版嵁搴撹繛鎺?
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 鏌ヨ瑕佸垹闄ょ殑璁板綍
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "File not found",
                    "data": None
                }), 404

            record = dict(record)

            # 鑾峰彇鏂囦欢璺緞骞跺垹闄ゅ疄闄呮枃浠?
            file_path = Path(BASE_DIR / "videoFile" / record['file_path'])
            if file_path.exists():
                try:
                    file_path.unlink()  # 鍒犻櫎鏂囦欢
                    print(f"鉁?瀹為檯鏂囦欢宸插垹闄? {file_path}")
                except Exception as e:
                    print(f"鈿狅笍 鍒犻櫎瀹為檯鏂囦欢澶辫触: {e}")
                    # 鍗充娇鍒犻櫎鏂囦欢澶辫触锛屼篃瑕佺户缁垹闄ゆ暟鎹簱璁板綍锛岄伩鍏嶆暟鎹笉涓€鑷?
            else:
                print(f"鈿狅笍 瀹為檯鏂囦欢涓嶅瓨鍦? {file_path}")

            # 鍒犻櫎鏁版嵁搴撹褰?
            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {
                "id": record['id'],
                "filename": record['filename']
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')

    if not account_id or not account_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing account ID",
            "data": None
        }), 400

    account_id = int(account_id)

    try:
        # 鑾峰彇鏁版嵁搴撹繛鎺?
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 鏌ヨ瑕佸垹闄ょ殑璁板綍
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "account not found",
                    "data": None
                }), 404

            record = dict(record)

            # 鍒犻櫎鍏宠仈鐨刢ookie鏂囦欢
            if record.get('filePath'):
                cookie_file_path = Path(BASE_DIR / "cookiesFile" / record['filePath'])
                if cookie_file_path.exists():
                    try:
                        cookie_file_path.unlink()
                        print(f"鉁?Cookie鏂囦欢宸插垹闄? {cookie_file_path}")
                    except Exception as e:
                        print(f"鈿狅笍 鍒犻櫎Cookie鏂囦欢澶辫触: {e}")

            # 鍒犻櫎鏁版嵁搴撹褰?
            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account deleted successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": f"delete failed: {str(e)}",
            "data": None
        }), 500


# SSE 鐧诲綍鎺ュ彛
@app.route('/login')
def login():
    # 1 灏忕孩涔?2 瑙嗛鍙?3 鎶栭煶 4 蹇墜
    type = request.args.get('type')
    # 璐﹀彿鍚?
    id = request.args.get('id')

    # 妯℃嫙涓€涓敤浜庡紓姝ラ€氫俊鐨勯槦鍒?
    status_queue = Queue()
    active_queues[id] = status_queue

    def on_close():
        print(f"娓呯悊闃熷垪: {id}")
        del active_queues[id]
    # 鍚姩寮傛浠诲姟绾跨▼
    thread = threading.Thread(target=run_async_function, args=(type,id,status_queue), daemon=True)
    thread.start()
    response = Response(sse_stream(status_queue,), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # 鍏抽敭锛氱鐢?Nginx 缂撳啿
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/postVideo', methods=['POST'])
def postVideo():
    # 鑾峰彇JSON鏁版嵁
    data = request.get_json()

    if not data:
        return jsonify({"code": 400, "msg": "璇锋眰鏁版嵁涓嶈兘涓虹┖", "data": None}), 400

    # 浠嶫SON鏁版嵁涓彁鍙杅ileList鍜宎ccountList
    file_list = data.get('fileList', [])
    account_list = data.get('accountList', [])
    type = data.get('type')
    title = data.get('title')
    tags = data.get('tags')
    category = data.get('category')
    enableTimer = data.get('enableTimer')
    if category == 0:
        category = None
    productLink = data.get('productLink', '')
    productTitle = data.get('productTitle', '')
    thumbnail_path = data.get('thumbnail', '')
    is_draft = data.get('isDraft', False)  # 鏂板鍙傛暟锛氭槸鍚︿繚瀛樹负鑽夌

    videos_per_day = data.get('videosPerDay')
    daily_times = data.get('dailyTimes')
    start_days = data.get('startDays')

    # 鍙傛暟鏍￠獙
    if not file_list:
        return jsonify({"code": 400, "msg": "鏂囦欢鍒楄〃涓嶈兘涓虹┖", "data": None}), 400
    if not account_list:
        return jsonify({"code": 400, "msg": "璐﹀彿鍒楄〃涓嶈兘涓虹┖", "data": None}), 400
    if not type:
        return jsonify({"code": 400, "msg": "骞冲彴绫诲瀷涓嶈兘涓虹┖", "data": None}), 400
    if not title:
        return jsonify({"code": 400, "msg": "鏍囬涓嶈兘涓虹┖", "data": None}), 400

    # 鎵撳嵃鑾峰彇鍒扮殑鏁版嵁锛堜粎浣滀负绀轰緥锛?
    print("File List:", file_list)
    print("Account List:", account_list)

    try:
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_path, productLink, productTitle)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days)
            case _:
                return jsonify({"code": 400, "msg": f"涓嶆敮鎸佺殑骞冲彴绫诲瀷: {type}", "data": None}), 400

        # 杩斿洖鍝嶅簲缁欏鎴风
        return jsonify(
            {
                "code": 200,
                "msg": "鍙戝竷浠诲姟宸叉彁浜?,
                "data": None
            }), 200
    except Exception as e:
        print(f"鍙戝竷瑙嗛鏃跺嚭閿? {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"鍙戝竷澶辫触: {str(e)}",
            "data": None
        }), 500


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    # 鑾峰彇JSON鏁版嵁
    data = request.get_json()

    # 浠嶫SON鏁版嵁涓彁鍙?type 鍜?userName
    user_id = data.get('id')
    type = data.get('type')
    userName = data.get('userName')
    try:
        # 鑾峰彇鏁版嵁搴撹繛鎺?
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 鏇存柊鏁版嵁搴撹褰?
            cursor.execute('''
                           UPDATE user_info
                           SET type     = ?,
                               userName = ?
                           WHERE id = ?;
                           ''', (type, userName, user_id))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account update successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("update failed!"),
            "data": None
        }), 500

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400
    for data in data_list:
        # 浠嶫SON鏁版嵁涓彁鍙杅ileList鍜宎ccountList
        file_list = data.get('fileList', [])
        account_list = data.get('accountList', [])
        type = data.get('type')
        title = data.get('title')
        tags = data.get('tags')
        category = data.get('category')
        enableTimer = data.get('enableTimer')
        if category == 0:
            category = None
        productLink = data.get('productLink', '')
        productTitle = data.get('productTitle', '')
        is_draft = data.get('isDraft', False)

        videos_per_day = data.get('videosPerDay')
        daily_times = data.get('dailyTimes')
        start_days = data.get('startDays')
        # 鎵撳嵃鑾峰彇鍒扮殑鏁版嵁锛堜粎浣滀负绀轰緥锛?
        print("File List:", file_list)
        print("Account List:", account_list)
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                               start_days)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, productLink, productTitle)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days)
    # 杩斿洖鍝嶅簲缁欏鎴风
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200

# Cookie鏂囦欢涓婁紶API
@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({
                "code": 400,
                "msg": "娌℃湁鎵惧埌Cookie鏂囦欢",
                "data": None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                "code": 400,
                "msg": "Cookie鏂囦欢鍚嶄笉鑳戒负绌?,
                "data": None
            }), 400

        if not file.filename.endswith('.json'):
            return jsonify({
                "code": 400,
                "msg": "Cookie鏂囦欢蹇呴』鏄疛SON鏍煎紡",
                "data": None
            }), 400

        # 鑾峰彇璐﹀彿淇℃伅
        account_id = request.form.get('id')
        platform = request.form.get('platform')

        if not account_id or not platform:
            return jsonify({
                "code": 400,
                "msg": "缂哄皯璐﹀彿ID鎴栧钩鍙颁俊鎭?,
                "data": None
            }), 400

        # 浠庢暟鎹簱鑾峰彇璐﹀彿鐨勬枃浠惰矾寰?
        with sqlite3.connect(Path(BASE_DIR, "db", "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({
                "code": 500,
                "msg": "璐﹀彿涓嶅瓨鍦?,
                "data": None
            }), 404

        # 淇濆瓨涓婁紶鐨凜ookie鏂囦欢鍒板搴旇矾寰?
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)

        file.save(str(cookie_file_path))

        # 鏇存柊鏁版嵁搴撲腑鐨勮处鍙蜂俊鎭紙鍙€夛紝姣斿鏇存柊鏇存柊鏃堕棿锛?
        # 杩欓噷鍙互鏍规嵁闇€瑕佹坊鍔犻澶栫殑澶勭悊閫昏緫

        return jsonify({
            "code": 200,
            "msg": "Cookie鏂囦欢涓婁紶鎴愬姛",
            "data": None
        }), 200

    except Exception as e:
        print(f"涓婁紶Cookie鏂囦欢鏃跺嚭閿? {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"涓婁紶Cookie鏂囦欢澶辫触: {str(e)}",
            "data": None
        }), 500


# Cookie鏂囦欢涓嬭浇API
@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({
                "code": 500,
                "msg": "缂哄皯鏂囦欢璺緞鍙傛暟",
                "data": None
            }), 400

        # 楠岃瘉鏂囦欢璺緞鐨勫畨鍏ㄦ€э紝闃叉璺緞閬嶅巻鏀诲嚮
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR, "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({
                "code": 500,
                "msg": "闈炴硶鏂囦欢璺緞",
                "data": None
            }), 400

        if not cookie_file_path.exists():
            return jsonify({
                "code": 500,
                "msg": "Cookie鏂囦欢涓嶅瓨鍦?,
                "data": None
            }), 404

        # 杩斿洖鏂囦欢
        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )

    except Exception as e:
        print(f"涓嬭浇Cookie鏂囦欢鏃跺嚭閿? {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"涓嬭浇Cookie鏂囦欢澶辫触: {str(e)}",
            "data": None
        }), 500


# 鍖呰鍑芥暟锛氬湪绾跨▼涓繍琛屽紓姝ュ嚱鏁?
def run_async_function(type,id,status_queue):
    match type:
        case '1':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(xiaohongshu_cookie_gen(id, status_queue))
            loop.close()
        case '2':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_tencent_cookie(id,status_queue))
            loop.close()
        case '3':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(douyin_cookie_gen(id,status_queue))
            loop.close()
        case '4':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_ks_cookie(id,status_queue))
            loop.close()

# SSE 娴佺敓鎴愬櫒鍑芥暟
def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
        else:
            # 閬垮厤 CPU 鍗犳弧
            time.sleep(0.1)

if __name__ == '__main__':
    app.run(host='0.0.0.0' ,port=5409)

