"""Startup boundaries must keep test collection away from real configuration/data."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

BACKEND = Path(__file__).resolve().parents[1]


def run_isolated(source, tmp_path):
    environment = os.environ.copy()
    environment.update(
        PYTHONPATH=str(BACKEND),
        DATABASE_PATH=str(tmp_path / "unused.sqlite3"),
        ADMIN_EMAIL="startup@example.com",
        ADMIN_PASSWORD="synthetic-startup-password",
    )
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "unused.sqlite3").exists()


def test_importing_factory_does_not_load_environment_or_initialize_database(tmp_path):
    run_isolated("""
        import dotenv
        import sqlmodel

        def forbidden(*args, **kwargs):
            raise AssertionError("Factory import must not load configuration or initialize storage")

        dotenv.load_dotenv = forbidden
        sqlmodel.create_engine = forbidden
        sqlmodel.SQLModel.metadata.create_all = forbidden
        import app.main as main
        assert callable(main.create_app)
        assert not hasattr(main, "app")
    """, tmp_path)


def test_runtime_loads_configuration_before_creating_application(tmp_path):
    run_isolated("""
        import os
        import dotenv

        def forbidden(*args, **kwargs):
            raise AssertionError("Only the mocked runtime loader may read configuration")

        dotenv.load_dotenv = forbidden
        import app.main as main

        calls = []
        application = object()

        def load_configuration(path):
            assert path == main.ROOT / ".env"
            calls.append("configuration")
            os.environ["ADMIN_EMAIL"] = "configured@example.com"
            return True

        def create_application():
            calls.append("application")
            assert main.Settings.from_env().admin_email == "configured@example.com"
            return application

        dotenv.load_dotenv = load_configuration
        main.create_app = create_application
        import app.asgi as runtime
        assert runtime.app is application
        assert calls == ["configuration", "application"]
    """, tmp_path)
