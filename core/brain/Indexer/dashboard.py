import socket
import threading
import time
from flask import Flask, jsonify, request

from core.logger.logger import logger

try:
    from werkzeug.serving import make_server
    WERKZEUG_OK = True
except ImportError:
    WERKZEUG_OK = False


_flask_app = None
_server = None
_server_thread = None
_actual_port = None
_dashboard_lock = threading.Lock()


def find_free_port(start=8080, end=8095):
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def create_app():
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.before_request
    def _handle_preflight():
        if request.method == "OPTIONS":
            resp = jsonify({"status": "ok"})
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
            return resp

    @app.after_request
    def _cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        return response

    @app.route("/api/status")
    def api_status():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify({
                "progress": rag_engine.get_progress(),
                "folders": rag_engine.list_folders(),
                "summary": rag_engine.get_indexed_folders_summary()
            })
        except Exception as e:
            logger.error(f"Dashboard api_status failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/folders")
    def api_folders():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify({"folders": rag_engine.list_folders()})
        except Exception as e:
            logger.error(f"Dashboard api_folders failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/folders/add", methods=["POST"])
    def api_folder_add():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400
            from core.brain.RagEngine import rag_engine
            result = rag_engine.add_folder(path)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_folder_add failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/folders/remove", methods=["POST"])
    def api_folder_remove():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400
            from core.brain.RagEngine import rag_engine
            result = rag_engine.remove_folder(path)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_folder_remove failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/folders/reindex", methods=["POST"])
    def api_folder_reindex():
        try:
            data = request.get_json() or {}
            path = data.get("path", "").strip()
            if not path:
                return jsonify({"success": False, "error": "Path is required."}), 400

            from pathlib import Path
            import os
            try:
                resolved = str(Path(path).expanduser().resolve())
            except Exception:
                return jsonify({"success": False, "error": "Invalid path."}), 400

            if not os.path.isdir(resolved):
                return jsonify({"success": False, "error": "Folder does not exist."}), 400

            from core.brain.Indexer.config_store import config_store
            folders = config_store.load_folders()
            registered = any(f["path"] == resolved for f in folders)
            if not registered:
                return jsonify({"success": False, "error": "Folder not registered."}), 400

            from core.brain.RagEngine import rag_engine
            threading.Thread(target=rag_engine.reindex_folder, args=(resolved,), daemon=True).start()

            return jsonify({"success": True, "path": resolved, "message": "Reindex started in background."})
        except Exception as e:
            logger.error(f"Dashboard api_folder_reindex failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/filters")
    def api_filters_get():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.get_filters())
        except Exception as e:
            logger.error(f"Dashboard api_filters_get failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/filters", methods=["POST"])
    def api_filters_post():
        try:
            data = request.get_json() or {}
            from core.brain.RagEngine import rag_engine
            result = rag_engine.update_filters(data)
            status = 200 if result.get("success") else 400
            return jsonify(result), status
        except Exception as e:
            logger.error(f"Dashboard api_filters_post failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/filters/reset", methods=["POST"])
    def api_filters_reset():
        try:
            from core.brain.Indexer.config_store import config_store
            from core.brain.RagEngine import rag_engine
            config_store.reset_filters()
            new_filters = config_store.load_filters()
            rag_engine.filter_engine.reload(new_filters)
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Dashboard api_filters_reset failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/pause", methods=["POST"])
    def api_pause():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.pause_indexing())
        except Exception as e:
            logger.error(f"Dashboard api_pause failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/resume", methods=["POST"])
    def api_resume():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.resume_indexing())
        except Exception as e:
            logger.error(f"Dashboard api_resume failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/purge/all", methods=["POST"])
    def api_purge_all():
        try:
            from core.brain.RagEngine import rag_engine
            return jsonify(rag_engine.purge_all())
        except Exception as e:
            logger.error(f"Dashboard api_purge_all failed: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    return app


def start_dashboard(port=None):
    global _flask_app, _server, _server_thread, _actual_port

    with _dashboard_lock:
        if _server is not None:
            logger.info(f"Dashboard already running on port {_actual_port}.")
            return _actual_port

        _flask_app = create_app()
        if port is None:
            port = find_free_port()
        if port is None:
            logger.error("Dashboard: no free port found in range 8080-8095.")
            return None

        try:
            if WERKZEUG_OK:
                _server = make_server("127.0.0.1", port, _flask_app, threaded=True)
                _server_thread = threading.Thread(target=_server.serve_forever, name="JarvisDashboard", daemon=True)
                _server_thread.start()
            else:
                _server_thread = threading.Thread(
                    target=_flask_app.run,
                    kwargs={"host": "127.0.0.1", "port": port, "debug": False, "use_reloader": False, "threaded": True},
                    name="JarvisDashboard",
                    daemon=True
                )
                _server_thread.start()
                time.sleep(1)

            _actual_port = port
            logger.info(f"Indexer Dashboard API running at http://127.0.0.1:{port}")
            return port
        except Exception as e:
            logger.error(f"Dashboard start failed: {e}")
            _server = None
            _server_thread = None
            return None


def stop_dashboard():
    global _server, _server_thread, _actual_port

    with _dashboard_lock:
        if _server is not None:
            try:
                _server.shutdown()
            except Exception as e:
                logger.warning(f"Dashboard shutdown warning: {e}")
            _server = None
        if _server_thread is not None:
            try:
                _server_thread.join(timeout=3)
            except Exception as e:
                logger.warning(f"Dashboard thread join warning: {e}")
            _server_thread = None
        _actual_port = None
        logger.info("Indexer Dashboard stopped.")


def is_dashboard_running():
    return _server_thread is not None and _server_thread.is_alive()


def get_dashboard_port():
    return _actual_port


if __name__ == "__main__":
    import sys
    from pathlib import Path

    project_root = str(Path(__file__).resolve().parents[3])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    port = start_dashboard()
    if port:
        logger.info(f"Standalone dashboard API running on port {port}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_dashboard()
    else:
        logger.error("Failed to start standalone dashboard.")