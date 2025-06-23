from flask import request, session, jsonify, render_template, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from compliance_engine import extract_text, match_to_controls, evaluate_compliance
from datetime import datetime
import os, json, csv
from io import StringIO

UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'xml', 'png'}
MAX_UPLOADS = 5
MAX_FAILS_BEFORE_BLOCK = 3

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'qiso1234'

device_uploads = {}
ip_fail_tracker = {}

SECURITY_POLICY = """
QISO Sentinel AI Compliance Bot - Data Usage Policy

By uploading your documents, you agree that:
- Your uploaded data may be used to improve the compliance model over time.
- No personal identifiers are stored or shared.
- Data is strictly used within the context of ISO 27001 compliance learning.
- You must accept this policy to continue.
"""

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def setup_routes(app):

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/policy')
    def policy():
        return f"<pre>{SECURITY_POLICY}</pre><form method='post' action='/accept'><button type='submit'>I Accept Policy</button></form>"

    @app.route('/accept', methods=['POST'])
    def accept_policy():
        session['policy_accepted'] = True
        return "<script>window.location.href='/'</script>"

    @app.route('/agree', methods=['POST'])
    def agree_terms():
        doc_id = request.form.get('doc_id', 'unknown')
        agreement_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "ip": request.remote_addr,
            "doc_id": doc_id,
            "session": session.get('user_id', 'anonymous')
        }

        os.makedirs("data", exist_ok=True)
        with open("data/policy_acceptance_log.json", "a") as f:
            json.dump(agreement_data, f)
            f.write("\n")

        session['policy_accepted'] = True
        return jsonify({"status": "accepted"})

    @app.route('/upload', methods=['POST'])
    def upload():
        if not session.get('policy_accepted'):
            return jsonify({"error": "You must accept the data usage policy before uploading."}), 403

        device_id = request.remote_addr
        if ip_fail_tracker.get(device_id, 0) >= MAX_FAILS_BEFORE_BLOCK:
            return jsonify({"error": "Access temporarily blocked due to repeated failed uploads."}), 403

        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded."}), 400

        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({"error": "Invalid or unsupported file type."}), 400

        filename = secure_filename(file.filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

        text = extract_text(file_path)
        if text.startswith("Error"):
            return jsonify({"error": text}), 500

        results = match_to_controls(text)
        passed, failed, score, is_compliant = evaluate_compliance(results, text)

        upload_entry = {
            "filename": filename,
            "passed_controls": passed,
            "failed_controls": failed,
            "score": round(score, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "session": session.get('user_id', 'anonymous'),
            "ip": device_id
        }

        os.makedirs('data', exist_ok=True)
        with open('data/user_uploads.json', 'a') as f:
            json.dump(upload_entry, f)
            f.write("\n")

        result_path = 'data/approved.json' if score >= 0.8 else 'data/failed.json'
        with open(result_path, 'a') as f:
            json.dump(upload_entry, f)
            f.write("\n")

        if score < 0.8:
            ip_fail_tracker[device_id] = ip_fail_tracker.get(device_id, 0) + 1
        else:
            ip_fail_tracker[device_id] = 0

        device_uploads[device_id] = device_uploads.get(device_id, 0) + 1
        return jsonify(upload_entry)

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
                session['is_admin'] = True
                return redirect('/admin')
            else:
                flash('Invalid credentials')
        return render_template('admin_login.html')

    @app.route('/admin/logout')
    def admin_logout():
        session.pop('is_admin', None)
        return redirect('/')

    @app.route('/admin')
    def admin_dashboard():
        if not session.get('is_admin'):
            return redirect('/admin/login')
        return render_template('dashboard.html')

    @app.route('/admin/api/dashboard')
    def api_dashboard():
        try:
            with open("data/approved.json") as f:
                approved = [json.loads(line) for line in f]
        except FileNotFoundError:
            approved = []

        try:
            with open("data/failed.json") as f:
                failed = [json.loads(line) for line in f]
        except FileNotFoundError:
            failed = []

        fail_control_counter = {}
        for entry in failed:
            for ctrl in entry.get("failed_controls", []):
                fail_control_counter[ctrl] = fail_control_counter.get(ctrl, 0) + 1

        return jsonify({
            "total": len(approved) + len(failed),
            "approved": len(approved),
            "failed": len(failed),
            "failed_controls": fail_control_counter
        })

    @app.route('/admin/api/agreements')
    def api_agreements():
        try:
            with open("data/policy_acceptance_log.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []
        return jsonify(logs)

    @app.route('/admin/api/agreements/page/<int:page>')
    def paginated_agreements(page):
        page_size = 20
        try:
            with open("data/policy_acceptance_log.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []
        start = (page - 1) * page_size
        return jsonify(logs[start:start + page_size])

    @app.route('/admin/api/user-uploads')
    def api_user_uploads():
        try:
            with open("data/user_uploads.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []
        return jsonify(logs)

    @app.route('/admin/api/user-uploads/page/<int:page>')
    def paginated_uploads(page):
        page_size = 20
        try:
            with open("data/user_uploads.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []
        start = (page - 1) * page_size
        return jsonify(logs[start:start + page_size])

    @app.route('/admin/api/daily-stats')
    def api_daily_stats():
        try:
            with open("data/user_uploads.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []
        stats = {}
        for log in logs:
            day = log["timestamp"][:10]
            stats[day] = stats.get(day, 0) + 1
        return jsonify([{"date": k, "count": v} for k, v in sorted(stats.items())])

    @app.route('/admin/export/json')
    def export_json():
        try:
            with open("data/policy_acceptance_log.json") as f:
                return f.read()
        except FileNotFoundError:
            return jsonify([])

    @app.route('/admin/export/csv')
    def export_csv():
        try:
            with open("data/policy_acceptance_log.json") as f:
                logs = [json.loads(line) for line in f]
        except FileNotFoundError:
            logs = []

        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=["timestamp", "ip", "doc_id", "session"])
        writer.writeheader()
        writer.writerows(logs)
        output.seek(0)
        return send_file(
            output,
            mimetype='text/csv',
            download_name="agreement_logs.csv",
            as_attachment=True
        )
