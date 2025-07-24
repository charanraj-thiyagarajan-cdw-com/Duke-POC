## Duke Services: Technical Overview for IT Infrastructure

This document provides a technical overview of the `Duke-Backend` and `Duke-Central` application stacks, focusing on their architecture, dependencies, and operational configuration for support purposes.

### 1. System Architecture

The system consists of two primary applications, `Duke-Backend` and `Duke-Central`, which work together to process and store data from an Avigilon security system.

*   **Duke-Backend**: A proxy API that sits between the Avigilon server and the `Duke-Central` application. It forwards relevant data, such as appearance events, from Avigilon to `Duke-Central`.
*   **Duke-Central**: A two-part application for data analytics.
    *   **Central Backend**: An API that receives data from `Duke-Backend` and stores it in a MongoDB database.
    *   **Central Frontend**: A Streamlit web UI that queries the Central Backend to visualize the stored data.

The data flow is as follows:

```
(Avigilon Server) <--> [Duke-Backend] <--> [Duke-Central Backend] <--> (MongoDB Database)
                           (Port 8000)         (Port 8001)

                                                    ^
                                                    |
                                                    v
                                       [Duke-Central Frontend (UI)]
                                                (Port 8502)
```

### 2. Duke-Backend (`DukeFarmingBackend` Service)

This service acts as the primary proxy for the Avigilon API.

*   **Purpose**: To query the Avigilon system and forward specific events to the central analytics backend.
*   **Technology**: Python, FastAPI, Uvicorn.
*   **Application Path**: `C:\path\to\Duke-Backend`
*   **Network Port**: `8000` (TCP)
*   **Key Dependencies**:
    *   Network connectivity to the **Avigilon Server**.
    *   Network connectivity to the **Duke-Central Backend** (e.g., `http://<central-host>:8001`).
*   **Configuration**:
    *   The configuration is managed via an `.env` file located in the application's root directory (`C:\path\to\Duke-Backend\.env`).
    *   **Key Variables**: `AVIGILON_BASE`, `CENTRAL_BASE`, `AVIGILON_API_VERIFY_SSL`.
*   **Windows Service (NSSM) Configuration**:
    *   **Service Name**: `DukeFarmingBackend`
    *   **Path**: `C:\path\to\venv\Scripts\python.exe`
    *   **Startup Dir**: `C:\path\to\Duke-Backend`
    *   **Arguments**: `-m uvicorn app.main:app --host 0.0.0.0 --port 8000`
*   **Operational Notes**:
    *   For production environments, the `AVIGILON_API_VERIFY_SSL` variable in the `.env` file should be set to `True`, which requires a valid SSL certificate on the Avigilon server.

### 3. Duke-Central Services

This system is composed of two distinct Windows services that must run on the same machine or have network access to each other and to a MongoDB instance.

#### 3.1. Duke-Central Backend (`DukeCentralBackend` Service)

*   **Purpose**: To receive, store, and serve analytics data.
*   **Technology**: Python, FastAPI, Uvicorn.
*   **Application Path**: `C:\path\to\Duke-central`
*   **Network Port**: `8001` (TCP)
*   **Key Dependencies**:
    *   **CRITICAL**: This service requires a running **MongoDB database instance**. It will fail to start or operate correctly if it cannot connect to the database.
    *   Network connectivity to the MongoDB server.
*   **Configuration**:
    *   Managed via an `.env` file in the application root (`C:\path\to\Duke-central\.env`).
    *   **Key Variables**: `MONGODB_BASE`, `MONGODB_DB`.
*   **Windows Service (NSSM) Configuration**:
    *   **Service Name**: `DukeCentralBackend`
    *   **Path**: `C:\path\to\venv\Scripts\python.exe`
    *   **Startup Dir**: `C:\path\to\Duke-central`
    *   **Arguments**: `-m uvicorn app.main:app --host 0.0.0.0 --port 8001`
*   **Operational Notes**:
    *   **Troubleshooting**: If this service is failing, the first step is to verify that the `mongod` process is running and is network-accessible from the host server.

#### 3.2. Duke-Central Frontend (`DukeCentralFrontend` Service)

*   **Purpose**: A web-based user interface for data visualization.
*   **Technology**: Python, Streamlit.
*   **Application Path**: `C:\path\to\Duke-central`
*   **Network Port**: `8502` (TCP)
*   **Key Dependencies**:
    *   Network connectivity to the **Duke-Central Backend** service (e.g., `http://<central-host>:8001`).
*   **Configuration**:
    *   Managed via a `secrets.toml` file located at `C:\path\to\Duke-central\.streamlit\secrets.toml`.
    *   **Key Variable**: `API_BASE`.
*   **Windows Service (NSSM) Configuration**:
    *   **Service Name**: `DukeCentralFrontend`
    *   **Path**: `C:\path\to\venv\Scripts\python.exe`
    *   **Startup Dir**: `C:\path\to\Duke-central`
    *   **Arguments**: `-m streamlit run .\ui\Home.py --server.port 8502 --server.headless true`
*   **Operational Notes**:
    *   This service provides the user-facing web dashboard.
    *   If the UI is unresponsive or shows errors, verify that the `DukeCentralBackend` service is running and accessible.

### 4. Ancillary Developer Tools

In addition to the production services detailed above, a development tool named `Duke-Frontend` exists within the project ecosystem.

*   **Purpose**: This is an exploratory user interface used by developers to manually interact with the `Duke-Backend` service. It helps them test API endpoints and understand data from the Avigilon system during the development cycle.
*   **Status**: **This tool is strictly for development and is not part of the production environment.** It is run on-demand on developer workstations and does not require installation, monitoring, or support as part of the production infrastructure. It should not be confused with the production `Duke-Central Frontend` UI. 
