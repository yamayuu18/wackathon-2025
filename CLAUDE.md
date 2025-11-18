# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Run/Test Commands

### Environment Setup
- Install dependencies: `pip install -r requirements.txt`
- Create virtual environment: `uv venv` or `python -m venv .venv`
- Activate environment: `source .venv/bin/activate`

### Camera & S3 Upload (MFA Required)
- Run camera with S3 upload: `python camera/camera_to_s3_mfa.py`
- First run requires MFA code input (6 digits from authenticator app)
- Subsequent runs (within 12 hours) use cached credentials automatically
- Stop program: Press `Ctrl+C`

### Credential Cache Management
- Create test cache: `python camera/test_cache.py create`
- Check cache status: `python camera/test_cache.py check`
- Create expired cache: `python camera/test_cache.py expired`
- Delete cache: `python camera/test_cache.py delete`

### Lambda Validation Testing
- Run all tests: `python lambda/test_local.py`
- Tests include: valid waste categories, prohibited items, mixed scenarios, edge cases

## System Architecture

This is a Wackathon 2025 project for an emotion-aware trash bin system that validates proper waste disposal.

### High-Level Architecture Flow
1. **PC Camera** → Captures images periodically (5-second intervals)
2. **MFA Authentication** → AWS STS generates 12-hour temporary credentials
3. **AWS S3** → Stores uploaded images, triggers Lambda via S3 event
4. **AWS Rekognition** → Analyzes images using DetectLabels API
5. **Lambda Function** → Validates labels against allowed waste categories
6. **AWS Polly** → Generates voice feedback based on validation results
7. **Speaker** → Plays audio response to user

### Critical Implementation Details

**MFA Authentication Flow (Organizations SCP Requirement)**:
- AWS Organizations SCP blocks standard IAM credentials for S3 operations
- Solution: MFA + STS temporary credentials bypass SCP restrictions
- Credentials cached for 12 hours in `camera/.aws_temp_credentials.json`
- Auto-validation checks expiration (5-minute buffer before re-auth)

**Waste Validation Logic**:
- Confidence threshold: 70% (configurable in `lambda/waste_categories.py`)
- Categories: 燃えるゴミ, プラスチック, 缶・ビン, ペットボトル
- Prohibited items: batteries, electronics, medical waste, hazardous materials
- Validation returns appropriate voice message for Polly TTS

### Key Components

**camera/** - Image capture and S3 upload
- `config.py`: Centralized configuration with environment variable support
- `camera_to_s3_mfa.py`: Main script with MFA auth, credential caching, S3 upload
- `test_cache.py`: Utility for testing credential cache functionality
- `captured_images/`: Local storage directory (gitignored)

**lambda/** - Waste validation logic (local implementation, AWS deployment pending)
- `waste_categories.py`: Category definitions and Rekognition label mappings
- `waste_validator.py`: Core validation logic for Lambda function
- `mock_data.py`: 9 test cases covering valid/invalid/edge scenarios
- `test_local.py`: Local test runner (9/9 tests passing)

**obniz/** - Hardware integration
- `index.html`: HC-SR04 ultrasonic sensor integration with GAS backend
- Sends distance data to Google Apps Script URL every 60 seconds

**doc/** - System documentation
- `poitokun_mermaid.html`: Complete system flow diagram

### Configuration Management

All settings centralized in [camera/config.py](camera/config.py) using environment variables:

**Camera Settings**:
- `CAMERA_DEVICE_ID`: Camera device selection (default: 0)
- `IMAGE_WIDTH`, `IMAGE_HEIGHT`: Resolution (default: 1280x720)
- `CAPTURE_INTERVAL_SECONDS`: Capture interval (default: 5)
- `IMAGE_QUALITY`: JPEG quality 1-100 (default: 95)

**AWS Settings** (loaded from `.env` file):
- `AWS_REGION`: AWS region (default: ap-northeast-1)
- `S3_BUCKET_NAME`: S3 bucket for image storage
- `AWS_ACCESS_KEY_ID`: IAM user access key
- `AWS_SECRET_ACCESS_KEY`: IAM user secret key
- `MFA_SERIAL_NUMBER`: MFA device ARN (format: arn:aws:iam::ACCOUNT_ID:mfa/DEVICE_NAME)

**Security Note**: `.env` file contains actual credentials and is gitignored. Use `.env.example` as template.

### AWS Integration Status

**Completed**:
- S3 upload with MFA authentication
- Lambda validation logic (local implementation)
- Credential caching system
- Environment-based configuration

**Pending AWS Deployment**:
- Lambda function deployment to AWS
- S3 event trigger configuration
- Rekognition DetectLabels integration
- Polly text-to-speech integration

### Code Style
- Type hints: Use `Final`, `Optional`, `list[Type]` for all parameters and returns
- Import ordering: PEP 8 (standard library → third-party → local modules)
- Docstrings: Google-style with Parameters and Returns sections
- Constants: UPPERCASE with Final annotation
- Naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Specific exceptions with clear error messages
