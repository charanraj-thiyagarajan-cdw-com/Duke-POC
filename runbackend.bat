cd C:\Users\Administrator\Documents\Duke-server-code
venv\Scripts\activate
cd Duke-Backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
