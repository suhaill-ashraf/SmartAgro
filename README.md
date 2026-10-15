# SmartAgro — AI-Based Spray Scheduler

> A weather-aware, AI-assisted Android application that helps apple growers in Kashmir decide **when to spray, what to spray, and when to wait**.

SmartAgro combines the apple spray-schedule guidelines published by Sher-e-Kashmir University of Agricultural Sciences and Technology of Kashmir (SKUAST-K) with current and forecast weather conditions. It provides a daily spray recommendation—**Spray, Delay, or Skip**—along with supporting information, scheduling tools, spray records, reports, notifications, and an in-app AI assistant.

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Technology Stack](#technology-stack)
- [System Architecture](#system-architecture)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Typical User Workflow](#typical-user-workflow)
- [Project Scope and Limitations](#project-scope-and-limitations)
- [Future Enhancements](#future-enhancements)
- [Academic Project](#academic-project)
- [Disclaimer](#disclaimer)

---

## Overview

Apple cultivation is an important part of Kashmir's agricultural economy. Although established spray schedules help growers identify treatments associated with different growth stages, a fixed schedule cannot account for day-to-day changes in weather. Rain may wash a treatment off, strong wind can cause spray drift, and unsuitable temperatures may affect application efficacy or damage foliage.

SmartAgro is designed to support this time-sensitive decision. The Android application retrieves weather information, evaluates agronomic safety rules, and uses a Random Forest classifier as an additional decision component. Recommendations are linked to the orchard's current growth stage and the project's SKUAST-K-based spray reference data.

The project was developed as a **Master of Computer Applications (MCA) final-year project** at the Department of Computer Science, University of Kashmir.

## Problem Statement

Traditional spray decisions often rely on a fixed seasonal calendar and the grower's personal experience. These methods do not automatically account for live weather, and they may offer limited support for maintaining spray records or remembering upcoming applications.

SmartAgro addresses this gap by bringing weather information, guideline-based spray details, decision support, and orchard record-keeping together in one mobile application.

## Key Features

- **Daily spray decision:** Presents a recommendation to spray, delay, or skip, with a reason.
- **Weather integration:** Retrieves current weather and forecast data for the orchard location.
- **Growth-stage guidance:** Displays the chemical, dosage, target pests or diseases, spray window, and cautions recorded for the selected growth stage.
- **Rule-based safety checks:** Evaluates rain, wind, temperature, and the minimum interval since the previous spray.
- **Machine-learning component:** Uses a scikit-learn Random Forest classifier to support the decision process.
- **Yearly spray calendar:** Generates a schedule based on the orchard profile and spray reference data.
- **Spray history:** Lets users record sprays as completed, postponed, or skipped, with notes.
- **Monthly reports:** Summarizes spray activity and schedule compliance.
- **Notifications:** Provides a daily summary of the next day's spray outlook.
- **AI assistant:** Uses the Grok language-model API to answer spraying-related questions in plain language, with orchard and weather context.
- **Multi-user support:** Provides authentication and separates users' profiles and records.
- **Cloud-hosted backend:** Makes the REST API accessible to the Android application over the internet.

## How It Works

SmartAgro uses a two-stage decision process:

1. **Collect inputs.** The system uses the orchard profile, current growth stage, last spray date, minimum spray interval, and available weather information.
2. **Apply agronomic rules.** Rule-based checks evaluate rain, wind, temperature, and spray-interval constraints.
3. **Evaluate the decision.** When conditions fall into the decision process's less-clear range, the Random Forest classifier contributes to the final recommendation.
4. **Return guidance.** The application displays the recommendation and its reason, along with the spray information associated with the current growth stage.
5. **Record and plan.** Users can maintain spray logs, view the calendar and reports, check forecasts, and consult the assistant.

The exact thresholds and decision logic are defined by the project implementation and its agronomic reference data.

## Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Android application | Kotlin | Native Android development |
| User interface | Jetpack Compose | Declarative mobile UI |
| Android architecture | MVVM | Separation of UI state and application logic |
| Android networking | Retrofit | Communication with the REST API |
| Backend | Python, Flask | REST API and server-side application logic |
| Database | SQLite | User accounts, orchard profiles, spray logs, reference data, settings, and notifications |
| Machine learning | scikit-learn, Random Forest | Classification of spray decisions |
| Weather service | OpenWeatherMap API | Current conditions and forecast data |
| AI assistant | Grok API | Natural-language answers to spraying questions |
| Backend hosting | PythonAnywhere | Cloud deployment of the Flask API |
| Android development | Android Studio | Android implementation, builds, and testing |
| Backend development | PyCharm | Python development and debugging |

## System Architecture

SmartAgro follows a client–server architecture.

```text
┌──────────────────────────────────┐
│       Android Application        │
│ Kotlin · Jetpack Compose · MVVM  │
│                                  │
│ Home · Weather · Calendar        │
│ Logs · Reports · Notifications   │
│ AI Assistant · Profile           │
└────────────────┬─────────────────┘
                 │ HTTPS/HTTP REST API
                 │ JSON · Retrofit
                 ▼
┌──────────────────────────────────┐
│        Flask Backend (Python)    │
│                                  │
│ Authentication and Profiles      │
│ Spray Decision Engine            │
│ Scheduling and Reporting         │
│ Spray Logs and Notifications     │
│ AI Assistant Integration         │
└───────┬──────────────┬───────────┘
        │              │
        ▼              ▼
┌───────────────┐  ┌────────────────────┐
│ SQLite        │  │ External Services  │
│ Application   │  │ OpenWeatherMap     │
│ Data          │  │ Grok API           │
└───────────────┘  └────────────────────┘

Decision components:
  • Rule-based agronomic checks
  • scikit-learn Random Forest classifier
  • SKUAST-K-based spray reference data
```

The backend is designed as a platform-neutral REST API, while the current client is a native Android application.

## Getting Started

### Prerequisites

To work with the project, you will generally need:

- **Android development:** Android Studio and a compatible Android SDK.
- **Backend development:** Python and `pip`.
- **Services:** An OpenWeatherMap API key and the credentials/configuration required for the Grok API integration.
- **Source code:** The Android and Flask backend project files.

> **Repository note:** This README is based on the project documentation. The documentation does not specify the source repository URL, exact Python version, dependency-file names, Android SDK version, or all environment-variable names. Use the actual project files as the source of truth for these details.

### 1. Obtain the source code

Clone the repository if one has been created, or open the project source provided by the project team.

```bash
git clone <repository-url>
cd <repository-directory>
```

Replace the placeholders with the actual repository URL and directory. If you received the source code as an archive, extract it and open the extracted project instead.

### 2. Set up the backend

Navigate to the backend directory—the directory containing the Flask application—and create a virtual environment.

```bash
python -m venv .venv
```

Activate the environment:

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS:**
```bash
source .venv/bin/activate
```

Install the dependencies using the dependency file supplied with the backend. For example, if the project contains a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

Configure the required API credentials and other settings using the configuration method already implemented in the backend. Then start the Flask application using the project's actual entry point and development instructions.

> The command to start the server depends on the backend's file and application names; check the source code before choosing a command.

### 3. Set up the Android application

1. Open the Android project in Android Studio.
2. Allow Gradle to sync and download the required dependencies.
3. Locate the API base URL configuration and set it to the address of your running Flask backend.
4. Ensure the backend is reachable from the device or emulator.
5. Build and run the application on an Android emulator or a physical Android device.

For a physical device, the backend address must be reachable from that device. A loopback address such as `localhost` refers to the device itself, not automatically to the development computer.

### 4. Verify the integration

After both components are configured:

1. Register or log in to the application.
2. Create or update an orchard profile.
3. Check that weather data can be retrieved.
4. Review the daily spray recommendation and its explanation.
5. Try the calendar, spray logging, reports, notifications, and assistant features.

The exact setup steps may differ depending on the supplied source tree and deployment configuration.

## Configuration

SmartAgro depends on external services for weather information and AI-assisted responses. Before running the full application, check the backend configuration and provide the required credentials.

| Configuration | Purpose |
|---|---|
| OpenWeatherMap API key | Retrieves current weather and forecast information |
| Grok API credentials | Enables the in-app language-model assistant |
| Backend/API base URL | Allows the Android app to communicate with the Flask server |
| Database location | Determines where the SQLite database is stored |
| Model/data files | Ensures the trained Random Forest model and required reference data are available to the backend |

**Security recommendations**

- Do not commit API keys, access tokens, passwords, or private configuration files to version control.
- Keep secrets in environment variables or an appropriate local configuration mechanism.
- Do not use production credentials in public examples or screenshots.
- Ensure that the Android application points to the intended backend environment.
- Follow the project's existing authentication and deployment configuration rather than assuming variable names or file paths.

## Typical User Workflow

1. **Sign in:** Register or log in to access the user's profile and records.
2. **Configure the orchard:** Enter the orchard information, location, current growth stage, last spray date, and minimum spray interval.
3. **Review today's decision:** Read the spray/delay/skip recommendation, the reason, and the stage-specific spray information.
4. **Check the weather:** Review current conditions and the multi-day forecast.
5. **Plan applications:** Use the yearly calendar to review upcoming spray stages.
6. **Maintain records:** Mark a spray as done, postponed, or skipped and add notes when needed.
7. **Review performance:** Use monthly reports and spray history to review activity and schedule compliance.
8. **Get guidance:** Use notifications and the in-app assistant for additional information.

## Project Scope and Limitations

SmartAgro is currently focused on **apple orchards in Kashmir** and uses spray-schedule reference data based on SKUAST-K guidelines. It is a decision-support application; it does not operate spraying equipment or replace a grower's professional agronomic judgment.

Important limitations documented for the project:

- **Synthetic ML training data:** The Random Forest classifier was trained on synthetically generated conditions whose labels come from a scoring function. Its measured accuracy therefore reflects how well it reproduces that designed logic; it does not demonstrate real-world spray-success prediction.
- **Region and crop scope:** The current reference data is specific to apple cultivation in Kashmir.
- **Internet dependency:** Live weather, recommendations that depend on online services, and the AI assistant require connectivity.
- **Weather-data dependency:** Recommendations depend in part on the accuracy and availability of the external weather service.
- **Android-only client:** The current mobile application is native Android.
- **Orchard representation:** The documented profile represents a single location and growth stage at a time; it does not fully model large orchards divided into multiple blocks.
- **No automatic field verification:** The system cannot independently confirm that a spray was applied; records depend on user input.

These limitations should be considered when interpreting recommendations and model-performance results.

## Future Enhancements

Potential directions identified in the project documentation include:

- Train and evaluate the model using real orchard observations and spray outcomes.
- Extend the reference data to other regional crops, such as pears, cherries, and walnuts.
- Adapt the application to apple-growing regions with different local guidelines.
- Develop an iOS client using the existing REST API.
- Add offline support for cached schedules and recent advice.
- Support multiple orchard blocks with different growth stages.
- Expand local-language support throughout the interface.
- Improve seasonal and year-over-year reporting.
- Integrate orchard-level weather sensors or additional data sources.
- Further enhance the AI assistant and its contextual guidance.

## Academic Project

**Project:** SmartAgro — AI-Based Spray Scheduler  
**Degree:** Master of Computer Applications (MCA)  
**Department:** Department of Computer Science  
**Institution:** University of Kashmir, Srinagar, Jammu and Kashmir  
**Academic Session:** 2025–2026  

**Project team**
- Suhail Ashraf Nengroo
- Areka Ayub
- Haris Khursheed

**Project Supervisor:** Dr. Sajid Yousuf Bhat

## Disclaimer

SmartAgro is an academic decision-support prototype. Its recommendations are based on the project's implementation, available weather data, and the spray reference information incorporated into the system. They should not be treated as a substitute for current local agricultural guidance, product-label instructions, or advice from a qualified agricultural professional.

Always verify chemical selection, dosage, timing, compatibility, and safety precautions against authoritative and up-to-date guidance before applying any treatment. The machine-learning component has not been established by the project documentation as a validated predictor of real-world spray outcomes.

---

*SmartAgro — bringing weather-aware decision support and spray record-keeping to apple growers in Kashmir.*
