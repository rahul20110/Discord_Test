# Discord Test

## Overview
It includes a **Decision Engine** and a **Discord Bot** for managing user roles and permissions. It leverages predefined criteria and rules to automate decision-making and interactions within a Discord server.

## Project Structure
```
src/
├── Decision_Engine/
│   ├── criteria.json           # Rules and criteria for decision making
│   ├── decision_engine.py      # Main script for decision processing
│   ├── image.png               # Architecture overview
│   ├── requirements.txt        # Dependencies for the Decision Engine
│   ├── role_change_history.json# Log of role changes
│   ├── role_hierarchy.json     # Defines the role hierarchy
│   ├── role_requests.json      # Tracks role change requests
│   ├── tool.py                 # Additional utility functions
│   ├── user_stats.json         # Stores user statistics
│
├── Discord_Bot/
│   ├── bot.py                  # Main bot script
│   ├── criteria.json           # Rules for role management
│   ├── role_change_history.json# Log of role changes
│   ├── role_hierarchy.json     # Defines Discord role structure
│   ├── role_requests.json      # Tracks role requests
│   ├── user_stats.json         # Stores Discord user statistics
│
├── .env                         # Environment variables file
```

## Setup Instructions
### 1. Install Dependencies
Make sure you have Python installed. Install required dependencies using the following command:
```bash
pip install -r Decision_Engine/requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory and define the necessary variables:
```
DISCORD_TOKEN=your_bot_token_here
GOOGLE_API_KEY=your_google_api_key_here
```

### 3. Running the Decision Engine
To execute the decision-making script:
```bash
python Decision_Engine/decision_engine.py
```

### 4. Running the Discord Bot
To start the Discord bot:
```bash
python Discord_Bot/bot.py
```

## Usage
- The **Decision Engine** automates role assignments based on defined criteria.
- The **Discord Bot** interacts with users, processes role requests, and maintains role hierarchy.
