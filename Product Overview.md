# Duke System: Product Overview

## 1. Introduction

The Duke System is a data integration and analytics platform designed to work with the Avigilon security system. Its primary function is to ingest security event data, enrich it with advanced facial recognition capabilities via AWS Rekognition, and provide a user interface for visualizing and analyzing the results.

This document provides a high-level overview of the system's purpose, components, and data flow. For more detailed technical information, please refer to the documents linked in the "Further Reading" section.

## 2. System Components

The platform is built on a microservices-style architecture composed of two main production applications and one developer tool.

*   **`Duke-Backend`**: This is the core data processing engine. It has two primary responsibilities:
    1.  **Data Ingestion**: It periodically polls the Avigilon API to fetch new security events.
    2.  **Facial Recognition Orchestration**: It processes stored event images using AWS Rekognition to identify and index faces.

*   **`Duke-Central`**: This application serves as the central hub for data storage and visualization. It is composed of two parts:
    *   **Central Backend**: An API that receives data from `Duke-Backend` and persists it in a MongoDB database.
    *   **Central Frontend**: The production web UI that users interact with to view dashboards and analyze the enriched event data.

*   **`Duke-Frontend` (Developer Tool)**: A separate, non-production Streamlit application used by developers to manually test and explore the Avigilon API via the `Duke-Backend`. **This tool is not part of the deployed production system.**

## 3. High-Level Data Lifecycle

The end-to-end process for handling data can be summarized in three main phases:

### Phase 1: Ingestion - Capturing Event Data

The `Duke-Backend` service uses a hybrid strategy to pull data from Avigilon. It runs two parallel schedulers to poll two different API endpoints:

1.  **High-Quality Appearances**: Polls `/api/appearance-search` for a low volume of high-quality events suitable for facial recognition.
2.  **High-Volume Motion**: Polls `/api/events` for a high volume of general motion events to ensure comprehensive activity logging.

All captured data is forwarded to `Duke-Central`, which stores it in different MongoDB collections based on the source.

> For a detailed explanation of this hybrid strategy, see [Technical Avigilon API Data Flow](Technical%20Avigilon%20API%20Data%20Flow.md).

### Phase 2: Processing - Facial Recognition

A separate scheduled job within `Duke-Backend` runs periodically to process events that have been stored but not yet analyzed.

1.  It requests a batch of unprocessed events from `Duke-Central`.
2.  For each event, it decodes the image and sends it to **AWS Rekognition** to search for existing faces or index new ones.
3.  The recognition results (e.g., `FaceId`, `status: matched`) are collected.
4.  The results are sent back to `Duke-Central` in a batch to update the event records in MongoDB.

> The complete sequence, including API calls and interactions, is detailed in the [Technical Integration Guide](Technical%20Integration%20Guide.md).

### Phase 3: Visualization - User Interaction

Once the data is processed and enriched with recognition metadata, it becomes available in the `Duke-Central Frontend`. Users can log in to this web interface to view dashboards, search for events, and analyze security trends.

## 4. Architecture and Further Reading

The Duke System is built primarily with Python, using FastAPI for the backend APIs and Streamlit for the user interfaces. It relies on MongoDB for data persistence.

For more specific information, please consult the following documents:

*   **For End-to-End Data Flow**:
    *   [Technical Integration Guide](Technical%20Integration%20Guide.md) - Details the entire lifecycle from ingestion to final storage after recognition.
*   **For Data Ingestion Details**:
    *   [Technical Avigilon API Data Flow](Technical%20Avigilon%20API%20Data%20Flow.md) - Explains the hybrid polling strategy for Avigilon APIs.
*   **For IT and Operations**:
    *   [Technical Overview](Technical%20Overview.md) - Provides infrastructure, deployment, and service configuration details for IT support.
*   **For Developers**:
    *   [Duke-Frontend/Technical Overview](https://github.com/mscdw/Duke-frontend/blob/main/Technical%20Overview.md) - Describes the purpose and usage of the developer-facing testing tool.
