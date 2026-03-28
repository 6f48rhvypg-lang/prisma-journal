"""
ComfyUI Workflow Builder for Prism-Style Artwork Generation

This module creates ComfyUI API-compatible workflow JSON for generating
soft pastel prism-style abstract artwork for journal entries.
"""

import json
import random
from typing import Optional


def create_prism_workflow(prompt: str, seed: Optional[int] = None, width: int = 768, height: int = 768) -> dict:
    """
    Create a ComfyUI workflow for generating soft pastel prism-style artwork.
    
    Args:
        prompt: The text prompt describing the desired artwork
        seed: Random seed for reproducibility (auto-generated if None)
        width: Image width (default 768)
        height: Image height (default 768)
    
    Returns:
        dict: ComfyUI API-compatible workflow
    """
    if seed is None:
        seed = random.randint(1, 2**32 - 1)
    
    # Base prompt for prism style
    base_prompt = "soft pastel abstract gradients, light refraction through prism, ethereal dreamy atmosphere, gentle color transitions, luminous glow, subtle light rays, peaceful serene mood, abstract geometric light patterns, soft focus, artistic abstract composition, high quality, detailed"
    
    # Combine with user prompt
    full_prompt = f"{base_prompt}, {prompt}" if prompt else base_prompt
    
    # Negative prompt to avoid unwanted elements
    negative_prompt = "text, watermark, signature, blurry, low quality, distorted, dark, gloomy, harsh colors, aggressive, violent, people, faces, specific objects, photorealistic, 3d render, photography"
    
    workflow = {
        "1": {
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {
                "title": "Load Checkpoint"
            }
        },
        "2": {
            "inputs": {
                "text": full_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {
                "title": "CLIP Text Encode (Prompt)"
            }
        },
        "3": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {
                "title": "CLIP Text Encode (Negative Prompt)"
            }
        },
        "4": {
            "inputs": {
                "seed": seed,
                "steps": 30,
                "cfg": 7.5,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0]
            },
            "class_type": "KSampler",
            "_meta": {
                "title": "KSampler"
            }
        },
        "5": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage",
            "_meta": {
                "title": "Empty Latent Image"
            }
        },
        "6": {
            "inputs": {
                "samples": ["4", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {
                "title": "VAE Decode"
            }
        },
        "7": {
            "inputs": {
                "filename_prefix": "journal_artwork",
                "images": ["6", 0]
            },
            "class_type": "SaveImage",
            "_meta": {
                "title": "Save Image"
            }
        }
    }
    
    return workflow


def create_prism_workflow_with_refiner(prompt: str, seed: Optional[int] = None, width: int = 768, height: int = 768) -> dict:
    """
    Create a ComfyUI workflow using SDXL Base + Refiner for higher quality prism artwork.
    
    Args:
        prompt: The text prompt describing the desired artwork
        seed: Random seed for reproducibility (auto-generated if None)
        width: Image width (default 768)
        height: Image height (default 768)
    
    Returns:
        dict: ComfyUI API-compatible workflow with refiner
    """
    if seed is None:
        seed = random.randint(1, 2**32 - 1)
    
    # Base prompt for prism style
    base_prompt = "soft pastel abstract gradients, light refraction through prism, ethereal dreamy atmosphere, gentle color transitions, luminous glow, subtle light rays, peaceful serene mood, abstract geometric light patterns, soft focus, artistic abstract composition, high quality, detailed"
    
    # Combine with user prompt
    full_prompt = f"{base_prompt}, {prompt}" if prompt else base_prompt
    
    # Negative prompt
    negative_prompt = "text, watermark, signature, blurry, low quality, distorted, dark, gloomy, harsh colors, aggressive, violent, people, faces, specific objects, photorealistic, 3d render, photography"
    
    # Advanced workflow with base + refiner
    workflow = {
        # Load Base Model
        "1": {
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Base Checkpoint"}
        },
        # Load Refiner Model
        "2": {
            "inputs": {
                "ckpt_name": "sd_xl_refiner_1.0.safetensors"
            },
            "class_type": "CheckpointLoaderSimple",
            "_meta": {"title": "Load Refiner Checkpoint"}
        },
        # Encode positive prompt with base
        "3": {
            "inputs": {
                "text": full_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Base CLIP Text Encode (Prompt)"}
        },
        # Encode negative prompt with base
        "4": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["1", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Base CLIP Text Encode (Negative)"}
        },
        # Encode positive prompt with refiner
        "5": {
            "inputs": {
                "text": full_prompt,
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Refiner CLIP Text Encode (Prompt)"}
        },
        # Encode negative prompt with refiner
        "6": {
            "inputs": {
                "text": negative_prompt,
                "clip": ["2", 1]
            },
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "Refiner CLIP Text Encode (Negative)"}
        },
        # Empty latent image
        "7": {
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1
            },
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Empty Latent Image"}
        },
        # Base sampler (20 steps, 80% denoise)
        "8": {
            "inputs": {
                "seed": seed,
                "steps": 20,
                "cfg": 7.5,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 0.8,
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["7", 0]
            },
            "class_type": "KSampler",
            "_meta": {"title": "Base KSampler"}
        },
        # Refiner sampler (10 steps, 20% denoise)
        "9": {
            "inputs": {
                "seed": seed + 1,
                "steps": 10,
                "cfg": 7.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 0.2,
                "model": ["2", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["8", 0]
            },
            "class_type": "KSampler",
            "_meta": {"title": "Refiner KSampler"}
        },
        # VAE Decode
        "10": {
            "inputs": {
                "samples": ["9", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode",
            "_meta": {"title": "VAE Decode"}
        },
        # Save Image
        "11": {
            "inputs": {
                "filename_prefix": "journal_artwork",
                "images": ["10", 0]
            },
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"}
        }
    }
    
    return workflow


def get_workflow_prompt_id(workflow: dict) -> str:
    """Extract the save image node ID from workflow for retrieving results."""
    for node_id, node_data in workflow.items():
        if node_data.get("class_type") == "SaveImage":
            return node_id
    return "11"  # Default to the save image node
