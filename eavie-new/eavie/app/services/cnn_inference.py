"""Custom PyTorch CNN: CUDA/CPU auto-select, preprocessing, batched scoring."""
from __future__ import annotations
import asyncio, io, os
from functools import lru_cache
from pathlib import Path
import structlog, torch, torch.nn as nn, torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from app.core.config import settings

log = structlog.get_logger()
CLASSES = ["ok", "scratch", "crack", "dent", "corrosion", "contamination"]

class _Block(nn.Module):
    def __init__(self, i: int, o: int):
        super().__init__()
        self.c1, self.b1 = nn.Conv2d(i, o, 3, padding=1, bias=False), nn.BatchNorm2d(o)
        self.c2, self.b2 = nn.Conv2d(o, o, 3, padding=1, bias=False), nn.BatchNorm2d(o)
    def forward(self, x):
        return F.max_pool2d(F.relu(self.b2(self.c2(F.relu(self.b1(self.c1(x)))))), 2)

class DefectCNN(nn.Module):
    def __init__(self, n_classes: int = len(CLASSES)):
        super().__init__()
        self.features = nn.Sequential(_Block(3, 32), _Block(32, 64), _Block(64, 128), _Block(128, 256))
        self.head = nn.Sequential(nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Dropout(0.3), nn.Linear(256, n_classes))
    def forward(self, x):
        return self.head(self.features(x))

class CNNEngine:
    def __init__(self, weights: str | None = None, size: int = 224, batch_size: int = 16):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.size, self.batch_size = size, batch_size
        self.model = DefectCNN().to(self.device)
        if weights and Path(weights).exists():
            self.model.load_state_dict(torch.load(weights, map_location=self.device))
            log.info("cnn_weights_loaded", path=weights)
        else:
            log.warning("cnn_weights_missing_random_init", path=weights)
        self.model.eval()
        self.tf = transforms.Compose([transforms.Resize((size, size)), transforms.ToTensor(),
                                      transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
        self.use_amp = self.device.type == "cuda"
        log.info("cnn_ready", device=str(self.device))

    def preprocess(self, img: Image.Image) -> torch.Tensor:
        return self.tf(img.convert("RGB"))

    @torch.inference_mode()
    def predict_images(self, images: list[Image.Image], names: list[str] | None = None) -> list[dict]:
        names = names or [f"img_{i}" for i in range(len(images))]
        out: list[dict] = []
        for s in range(0, len(images), self.batch_size):
            x = torch.stack([self.preprocess(i) for i in images[s:s + self.batch_size]]).to(self.device, non_blocking=True)
            with torch.autocast(self.device.type, enabled=self.use_amp):
                probs = F.softmax(self.model(x).float(), dim=1).cpu()
            conf, idx = probs.max(1)
            for j in range(len(conf)):
                lab = CLASSES[int(idx[j])]
                out.append({"path": names[s + j], "label": lab, "confidence": float(conf[j]), "defect": lab != "ok",
                            "probs": {c: round(float(p), 4) for c, p in zip(CLASSES, probs[j])}})
        return out

    def predict_bytes(self, blob: bytes, name: str = "upload") -> dict:
        return self.predict_images([Image.open(io.BytesIO(blob))], [name])[0]

    def predict_paths(self, paths: list[str]) -> list[dict]:
        imgs = []
        for p in paths:
            with Image.open(p) as im:
                imgs.append(im.copy())
        return self.predict_images(imgs, [os.path.basename(p) for p in paths])

    async def predict_paths_async(self, paths: list[str]) -> list[dict]:
        return await asyncio.to_thread(self.predict_paths, paths) if paths else []

@lru_cache(maxsize=1)
def get_engine() -> CNNEngine:
    return CNNEngine(weights=settings.CNN_WEIGHTS_PATH)
