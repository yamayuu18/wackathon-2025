# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run/Test Commands
- Install dependencies: `pip install -r requirements.txt`
- Run camera capture: `cd camera && python camera_capture.py`
- Stop program: Press `Ctrl+C`

## System Architecture

This is a Wackathon 2025 project for a trash bin system that recognizes emotions and validates proper waste disposal.

### High-Level Architecture Flow
1. **PC Camera** → Captures images periodically (5-second intervals)
2. **AWS S3** → Stores uploaded images, triggers Lambda
3. **AWS Rekognition** → Analyzes images using DetectLabels API
4. **Lambda Function** → Processes labels, matches against allowed waste types
5. **AWS Polly** → Generates voice feedback based on match results
6. **Speaker** → Plays audio response to user

### Key Components

**camera/** - Python scripts for image capture
- `config.py`: Central configuration (intervals, resolution, AWS settings)
- `camera_capture.py`: OpenCV-based periodic image capture to local storage
- `camera_to_s3.py`: (Future) S3 upload integration after AWS credentials are provided

**obniz/** - Hardware integration (distance sensor)
- `index.html`: obniz HC-SR04 ultrasonic sensor with GAS backend integration
- Sends distance data to Google Apps Script URL every 60 seconds

**doc/** - System documentation
- `poitokun_mermaid.html`: Complete system flow diagram showing hardware, AWS services, and Lambda processing logic

### Configuration Management

All runtime settings are centralized in [camera/config.py](camera/config.py):
- Camera device selection and resolution
- Capture interval timing
- Image quality and format
- AWS credentials (commented, pending provision from hackathon organizers)

### Future AWS Integration

When AWS environment is provided:
1. Uncomment and configure AWS settings in `config.py`
2. Implement `camera_to_s3.py` with boto3 S3 upload
3. Configure Lambda function to process S3 events
4. Integrate Rekognition DetectLabels and Polly text-to-speech

### Code Style
- Use type hints (Final, list[Type], etc.) for all parameters and returns
- Follow PEP 8 import ordering
- Google-style docstrings with Parameters/Returns sections
- Constants as UPPERCASE with Final annotation
