# Motivo - Humanoid Motion Control Project

A project combining web interface and Python backend for controlling humanoid motion using reward-based behaviors.

## Overview

This project implements a humanoid motion control system using:
- Web frontend (Vite + Lit + TypeScript)
- Python backend (Flask + WebSocket)
- Metamotivo model for humanoid motion generation
- Custom reward functions for behavior control

## Prerequisites

- Python 3.11 or higher
- Node.js 18+ and npm
- uv package manager (`pip install uv`)

## Installation

### Clone the Repository
```bash
git clone https://github.com/yourusername/motivo.git
cd motivo
```

### Python Setup
Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate  # Unix/MacOS
# OR
.venv\Scripts\activate     # Windows
```

Install dependencies:
```bash
uv pip install -r requirements.txt
```

### Frontend Setup
Install Node.js dependencies:
```bash
npm install
```

## Running the Project

1. Start the Python backend:
```bash
python webserver.py
```

2. In a new terminal, start the WebSocket server:
```bash
python 04_ws_example.py
```

3. Start the frontend development server:
```bash
npm run dev
```

4. Access the web interface at http://localhost:5173

## Project Structure

### Frontend
- `/src`: Frontend source code
  - `components/`: Lit components
  - `rewards/`: Reward configuration types and utilities
  - `my-element.ts`: Main application component
  - `index.css`: Global styles

### Backend
- `webserver.py`: Flask server for reward generation
- `04_ws_example.py`: WebSocket server for real-time motion control
- `env_setup.py`: Environment configuration
- `custom_rewards.py`: Custom reward functions

## Key Dependencies

### Python
- metamotivo
- flask
- flask-cors
- websockets
- torch
- numpy
- opencv-python
- humenv
- anthropic

### Frontend
- lit
- typescript
- vite

## Available Reward Types

The system supports various reward types for controlling humanoid motion:

### Basic Movement
- Walking
- Running
- Low walking

### Acrobatic Moves
- Jumping
- Rotations
- Headstand

### Poses
- Sitting
- Lying down
- Splits

### Arm Control
- Raise arms
- Combined movement with arm control

## License

MIT License

