"""Product image storage service backed by AppPaths."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

from backend.shared.app_paths import AppPaths


class ProductImageService:
    """Stores product images under the application data directory."""

    def __init__(self, paths: AppPaths | None = None) -> None:
        self._paths = (paths or AppPaths.from_environment()).ensure_directories()
        self._paths.product_images_dir.mkdir(parents=True, exist_ok=True)

    @property
    def images_dir(self) -> Path:
        return self._paths.product_images_dir

    def store_image(self, source_path: str) -> str:
        source = Path(source_path).expanduser()
        suffix = source.suffix.lower() or ".img"
        target = self.images_dir / f"prod_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{suffix}"
        shutil.copy(source, target)
        return str(target)
