# ComfyUI Integration Setup Guide

This guide explains how to set up ComfyUI for automatic artwork generation in the PrismA - Secure Journal App.

## Overview

The journal app now uses **ComfyUI** as the primary image generation backend, providing high-quality AI-generated artwork for your journal entries. The artwork is created automatically during entry analysis and features soft pastel prism-style gradients matching your reference aesthetic.

## Requirements

- Windows 10/11
- NVIDIA GPU with at least 8GB VRAM (RTX 3090/4090/5090 recommended)
- Python 3.10 or higher
- ComfyUI installed at `C:\ComfyUI`

## Installation

### Step 1: Install ComfyUI

1. Download ComfyUI from: https://github.com/comfyanonymous/ComfyUI
2. Extract to `C:\ComfyUI`
3. Install the required models:

**Required Models (place in `C:\ComfyUI\models\checkpoints\`):**
- `sd_xl_base_1.0.safetensors` - Base SDXL model
- `sd_xl_refiner_1.0.safetensors` - Refiner for higher quality (optional but recommended)

**Download Links:**
- SDXL Base: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- SDXL Refiner: https://huggingface.co/stabilityai/stable-diffusion-xl-refiner-1.0

### Step 2: Configure the Journal App

1. Copy `.env.example` to `.env` (if not already done):
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and ensure these settings are configured:
   ```env
   # ComfyUI Configuration
   COMFY_ENABLED=true
   COMFY_API_URL=http://127.0.0.1:8188
   COMFY_WORKFLOW_MODE=refiner  # Options: "base" or "refiner"
   COMFY_BASE_MODEL=sd_xl_base_1.0.safetensors
   COMFY_REFINER_MODEL=sd_xl_refiner_1.0.safetensors
   ```

### Step 3: Start ComfyUI

**Option A: Manual Start (for testing)**

1. Open Command Prompt
2. Navigate to ComfyUI:
   ```bash
   cd C:\ComfyUI
   ```
3. Start with API enabled:
   ```bash
   python main.py --listen --port 8188
   ```
4. Keep this window open - ComfyUI must be running for artwork generation

**Option B: Auto-Start on Boot (Recommended)**

1. Navigate to the journal app scripts folder:
   ```bash
   cd C:\Users\eiwen\journalapp\scripts
   ```

2. Run the setup script as Administrator:
   - Right-click `setup_autostart.bat`
   - Select "Run as administrator"
   - This adds ComfyUI to Windows Task Scheduler

3. To start ComfyUI immediately:
   - Double-click `start_comfyui.bat`

## How It Works

### Automatic Artwork Generation

When you click **"Finish Entry"** after writing a journal entry:

1. **Step 1**: AI analyzes emotions in your entry
2. **Step 2**: AI generates a summary and title
3. **Step 3**: AI identifies cognitive patterns
4. **Step 4**: **ComfyUI generates prism-style artwork** based on entry mood/themes

The artwork is automatically saved and displayed on your entry. Each entry gets a unique image with a randomized seed.

### Image Style

The artwork features:
- **Soft pastel gradients** matching your reference aesthetic
- **Light refraction** and prism effects
- **768x768 resolution** for high quality
- **Randomized seeds** for unique variations per entry
- **Privacy-preserving** - no personal content in the image, only abstract mood representation

### Workflow Modes

**Base Mode** (`COMFY_WORKFLOW_MODE=base`):
- Uses only SDXL Base model
- Faster generation (~15-20 seconds on RTX 5090)
- Good quality
- 30 sampling steps

**Refiner Mode** (`COMFY_WORKFLOW_MODE=refiner`) - **Recommended**:
- Uses SDXL Base + Refiner pipeline
- Higher quality with better detail
- Slightly slower (~25-35 seconds on RTX 5090)
- 20 base steps + 10 refiner steps

## Troubleshooting

### "Image generation failed" Error

1. **Check ComfyUI is running**:
   - Open browser to http://127.0.0.1:8188
   - If not accessible, start ComfyUI with `start_comfyui.bat`

2. **Check models are installed**:
   - Verify `sd_xl_base_1.0.safetensors` exists in `C:\ComfyUI\models\checkpoints\`
   - For refiner mode, also check `sd_xl_refiner_1.0.safetensors`

3. **Check `.env` configuration**:
   - Ensure `COMFY_ENABLED=true`
   - Verify `COMFY_API_URL` matches ComfyUI's address

### ComfyUI Won't Start

1. **Check Python is installed**:
   ```bash
   python --version
   ```

2. **Install dependencies**:
   ```bash
   cd C:\ComfyUI
   pip install -r requirements.txt
   ```

3. **Check GPU drivers**:
   - Update NVIDIA drivers to latest version
   - Verify CUDA is available: `nvidia-smi`

### Artwork Not Generated Automatically

1. **Check artwork is enabled** in Settings page
2. **Verify you're clicking "Finish Entry"** not "Save Without Analysis"
3. **Check browser console** for JavaScript errors
4. **Review app logs** for detailed error messages

### Slow Generation Times

- **Expected times** on RTX 5090:
  - Base mode: 15-20 seconds
  - Refiner mode: 25-35 seconds

- **To speed up**:
  - Switch to base mode: `COMFY_WORKFLOW_MODE=base`
  - Close other GPU-intensive applications
  - Ensure GPU is not thermally throttling

## Advanced Configuration

### Custom Model Names

If your model files have different names, update `.env`:

```env
COMFY_BASE_MODEL=your_base_model_name.safetensors
COMFY_REFINER_MODEL=your_refiner_model_name.safetensors
```

### Using Different Checkpoint Models

You can use any SDXL-compatible model:

1. Place the `.safetensors` file in `C:\ComfyUI\models\checkpoints\`
2. Update `COMFY_BASE_MODEL` in `.env`
3. Restart ComfyUI

### Disabling ComfyUI

To fall back to algorithmic art generation:

```env
COMFY_ENABLED=false
```

The app will then use the Python-based algorithmic art generator (fast but lower quality).

## File Locations

- **ComfyUI**: `C:\ComfyUI`
- **Models**: `C:\ComfyUI\models\checkpoints\`
- **Startup Script**: `C:\Users\eiwen\journalapp\scripts\start_comfyui.bat`
- **Auto-Start Setup**: `C:\Users\eiwen\journalapp\scripts\setup_autostart.bat`
- **Generated Artwork**: `C:\Users\eiwen\journalapp\app\static\uploads\`
- **Workflow Config**: `C:\Users\eiwen\journalapp\app\models\comfy_workflow.py`

## Support

For ComfyUI-specific issues:
- ComfyUI GitHub: https://github.com/comfyanonymous/ComfyUI
- Model downloads: https://huggingface.co/stabilityai

For journal app issues:
- Check the browser console for JavaScript errors
- Review the Flask app logs in the terminal
- Verify all environment variables in `.env`

## Summary

Once set up, your workflow is:

1. **Write journal entry** ✍️
2. **Click "Finish Entry"** ✅
3. **AI analyzes** and **generates artwork automatically** 🎨
4. **Enjoy your beautiful prism-style image!** ✨

The artwork appears on your entry page immediately and stays associated with that entry even when you edit the text.
