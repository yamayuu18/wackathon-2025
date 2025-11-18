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

**lambda/** - Waste validation and voice generation logic
- `waste_categories.py`: Category definitions and Rekognition label mappings
- `waste_validator.py`: Core validation logic with Polly integration
- `polly_config.py`: AWS Polly voice synthesis configuration
- `mock_data.py`: 9 test cases covering valid/invalid/edge scenarios
- `test_local.py`: Local test runner (9/9 tests passing)
- `waste_recognition.zip`: Deployment package for AWS Lambda

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
- Lambda function deployment to AWS with updated code
- S3 event trigger configuration
- IAM role permission updates for Polly and S3 voice bucket

## AWS Polly Integration

### Voice Synthesis Setup

The Lambda function now includes AWS Polly integration for generating voice feedback:

**Configuration** ([lambda/polly_config.py](lambda/polly_config.py)):
- Engine: `neural` (high-quality voice synthesis)
- Voice ID: `Takumi` (Japanese male voice)
- Output format: MP3 (24kHz sample rate)
- Voice bucket: `wackathon-2025-voice-responses` (configurable via environment variable)

**Audio File Naming**:
- Format: `voice_response_YYYYMMDD_HHMMSS.mp3`
- Storage: Separate S3 bucket for voice files

### Lambda Deployment Steps

1. **Create S3 Voice Bucket** (AWS Console or CLI):
   ```bash
   aws s3 mb s3://wackathon-2025-voice-responses --region ap-northeast-1
   ```

2. **Update Lambda IAM Role Permissions**:
   Add the following policies to the Lambda execution role:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "polly:SynthesizeSpeech"
         ],
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": [
           "s3:PutObject"
         ],
         "Resource": "arn:aws:s3:::wackathon-2025-voice-responses/*"
       }
     ]
   }
   ```

3. **Upload Lambda Function**:
   - Go to AWS Lambda Console
   - Select `waste-recognition-function`
   - Upload `lambda/waste_recognition.zip`
   - Handler: `waste_validator.lambda_handler`

4. **Set Environment Variables** (Lambda Console):
   - Key: `VOICE_BUCKET_NAME`
   - Value: `wackathon-2025-voice-responses`

5. **Test the Function**:
   - Upload test image to S3 images bucket
   - Check CloudWatch Logs for:
     - `[INFO] Polly音声合成開始`
     - `[INFO] 音声合成完了`
     - `[INFO] 音声URL生成完了`
   - Verify audio file created in voice bucket

### Response Format

The Lambda function now returns audio URL in the response:

```json
{
  "statusCode": 200,
  "body": {
    "is_valid": true,
    "message": "ありがとうございます！プラスチックとして正しく分別されています。",
    "audio_url": "https://wackathon-2025-voice-responses.s3.ap-northeast-1.amazonaws.com/voice_response_20251118_123456.mp3",
    "detected_items": ["Bottle (89.1%)"],
    "categories": ["プラスチック", "ペットボトル"],
    "prohibited_items": []
  }
}
```

### Troubleshooting

**Polly synthesis fails**:
- Check IAM role has `polly:SynthesizeSpeech` permission
- Verify VoiceId "Takumi" is available in ap-northeast-1 region
- Check CloudWatch Logs for detailed error messages

**S3 upload fails**:
- Verify voice bucket exists: `aws s3 ls s3://wackathon-2025-voice-responses`
- Check IAM role has `s3:PutObject` permission for voice bucket
- Ensure bucket is in same region as Lambda (ap-northeast-1)

**Audio URL returns null**:
- Check CloudWatch Logs for Polly/S3 errors
- Verify environment variable `VOICE_BUCKET_NAME` is set correctly
- Function will continue to work even if voice generation fails (message text is still returned)

### Common IAM Permission Errors

**Error: AccessDenied - polly:SynthesizeSpeech**
```
User: arn:aws:sts::438632968703:assumed-role/WackathonLambdaRole/wackathon-waste-recognition
is not authorized to perform: polly:SynthesizeSpeech
```
**Cause**: Lambda execution role (WackathonLambdaRole) lacks Polly permission
**Solution**: Add `polly:SynthesizeSpeech` to WackathonLambdaRole (not user policy)

**Error: AccessDenied - s3:PutObject on voice bucket**
```
is not authorized to perform: s3:PutObject on resource:
"arn:aws:s3:::wackathon-2025-voice-responses/voice_response_*.mp3"
```
**Cause**: Lambda execution role lacks S3 voice bucket write permission
**Solution**: Add `s3:PutObject` for `arn:aws:s3:::wackathon-2025-voice-responses/*` to WackathonLambdaRole

**Important**: Lambda execution role and user IAM policy are separate. Lambda functions use the execution role, not user credentials.

## IAM Permission Configuration

### Lambda Execution Role (WackathonLambdaRole)
Required permissions for Lambda function runtime:

| Service | Action | Resource | Purpose |
|---------|--------|----------|---------|
| Rekognition | `DetectLabels` | `*` | Image recognition |
| S3 | `GetObject` | `wackathon-2025-trash-images/*` | Read uploaded images |
| Polly | `SynthesizeSpeech` | `*` | Generate voice responses |
| S3 | `PutObject` | `wackathon-2025-voice-responses/*` | Save audio files |
| CloudWatch Logs | `CreateLogGroup`, `CreateLogStream`, `PutLogEvents` | `*` | Logging |

### IAM User Permissions
Required permissions for manual operations (camera upload, Lambda deployment):

| Operation | Action | Resource | Purpose |
|-----------|--------|----------|---------|
| Image upload | `s3:PutObject` | `wackathon-2025-trash-images/*` | Camera → S3 |
| Lambda update | `lambda:UpdateFunctionCode` | Lambda function ARN | Deploy code |
| IAM management | `iam:*` | Roles/Policies | Configure permissions |

**Key Distinction**: User policies do NOT affect Lambda execution. Lambda uses its execution role exclusively.

### Code Style
- Type hints: Use `Final`, `Optional`, `list[Type]` for all parameters and returns
- Import ordering: PEP 8 (standard library → third-party → local modules)
- Docstrings: Google-style with Parameters and Returns sections
- Constants: UPPERCASE with Final annotation
- Naming: snake_case for variables/functions, PascalCase for classes
- Error handling: Specific exceptions with clear error messages
