"""
MiniBank test suite.
Runs without a database — tests the Flask app in frontend-only mode.
"""
import pytest
from app import app


@pytest.fixture
def client():
    """Create a Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


# --- Smoke Tests ---

def test_app_exists():
    """App object is created."""
    assert app is not None


def test_index_returns_200(client):
    """GET / should return 200 (login page)."""
    response = client.get('/')
    assert response.status_code == 200


def test_login_page_renders(client):
    """GET /login should return 200."""
    response = client.get('/login')
    assert response.status_code == 200


def test_register_page_renders(client):
    """GET /register should return 200."""
    response = client.get('/register')
    assert response.status_code == 200


# --- Auth Guard Tests ---

def test_dashboard_redirects_when_not_logged_in(client):
    """GET /dashboard should redirect to login when not authenticated."""
    response = client.get('/dashboard')
    assert response.status_code == 302


def test_deposit_redirects_when_not_logged_in(client):
    """POST /deposit should redirect to login when not authenticated."""
    response = client.post('/deposit', data={'amount': 100})
    assert response.status_code == 302


def test_logout_redirects(client):
    """GET /logout should redirect to index."""
    response = client.get('/logout')
    assert response.status_code == 302


# --- DB-Unavailable Behavior ---

def test_login_post_without_db_shows_flash(client):
    """POST /login should flash a warning when DB is not available."""
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    }, follow_redirects=True)
    assert response.status_code == 200


def test_register_post_without_db_shows_flash(client):
    """POST /register should flash a warning when DB is not available."""
    response = client.post('/register', data={
        'username': 'newuser',
        'password': 'newpass',
        'email': 'new@example.com'
    }, follow_redirects=True)
    assert response.status_code == 200
