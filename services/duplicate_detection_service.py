"""
Service for detecting duplicate images using a 4-layer pipeline:
L1 — MD5 (exact copies)
L2 — pHash (brightness/contrast edits, resizes)
L3 — DINOv2 embeddings (crops, rotations, geometric transforms)
L4 — CLIP embeddings (heavy edits, filters, stylistic changes)

L1 results are returned as "Exact Duplicates".
L2+L3+L4 results are returned as "Near Duplicates".
Images matched in L1 are excluded from L2, L3, and L4.
"""

import hashlib
import io
from typing import Dict, List, Any, Tuple, Set
from collections import defaultdict

import numpy as np
import torch
import clip
import faiss
import imagehash
from PIL import Image
from transformers import AutoImageProcessor, Dinov2Model

from services.base import BaseService
from models.duplicate_detection_model import (
    DuplicateImage,
    DuplicateGroup,
    DuplicateCategory,
    DuplicateDetectionResponse,
)

# ── Module-level model loading (singleton) ──────────────────────────

_device = "cuda" if torch.cuda.is_available() else "cpu"

# CLIP ViT-B/32
_clip_model, _clip_preprocess = clip.load("ViT-B/32", device=_device)
_clip_model.eval()

# DINOv2-base feature extractor (768-dim, robust to rotations/crops)
_dino_processor = AutoImageProcessor.from_pretrained("facebook/dinov2-base")
_dino_model = Dinov2Model.from_pretrained("facebook/dinov2-base").to(_device)
_dino_model.eval()

# ── Union-Find ──────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ── Service ─────────────────────────────────────────────────────────

class DuplicateDetectionService(BaseService):

    # ── Fingerprint computation ──────────────────────────────────────

    def compute_md5(self, image_bytes: bytes) -> str:
        return hashlib.md5(image_bytes).hexdigest()

    def compute_phash(self, image_bytes: bytes) -> str:
        img = Image.open(io.BytesIO(image_bytes))
        return str(imagehash.phash(img))

    def compute_dino_embedding(self, image_bytes: bytes) -> List[float]:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        inputs = _dino_processor(images=img, return_tensors="pt").to(_device)
        with torch.no_grad():
            outputs = _dino_model(**inputs)
            embedding = outputs.last_hidden_state[:, 0].squeeze(0)  # CLS token, 768-dim
            embedding = embedding / embedding.norm()
        return embedding.cpu().tolist()

    def compute_clip_embedding(self, image_bytes: bytes) -> List[float]:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = _clip_preprocess(img).unsqueeze(0).to(_device)
        with torch.no_grad():
            embedding = _clip_model.encode_image(tensor).squeeze(0).float()
            embedding = embedding / embedding.norm()
        return embedding.cpu().tolist()

    def compute_image_fingerprints(self, image_bytes: bytes) -> Dict[str, Any]:
        return {
            "md5_hash": self.compute_md5(image_bytes),
            "phash": self.compute_phash(image_bytes),
            "image_embeddings_efficientnetb0": self.compute_dino_embedding(image_bytes),
            "image_embeddings": self.compute_clip_embedding(image_bytes),
        }

    # ── 4-layer detection ────────────────────────────────────────────

    def detect_duplicates(self, project_id: str, duplicate_threshold: float) -> DuplicateDetectionResponse:
        self.logger.info(f"Running duplicate detection for project {project_id}")

        # Fetch all images with their fingerprints
        response = (
            self.db.table("images")
            .select("id, image_url, md5_hash, phash, image_embeddings_efficientnetb0, image_embeddings")
            .eq("project_id", project_id)
            .execute()
        )
        images = response.data or []
        if len(images) < 2:
            return DuplicateDetectionResponse(
                project_id=project_id,
                exact_duplicates=DuplicateCategory(caption="Exact Duplicates", groups=[], total_groups=0, total_images=0),
                near_duplicates=DuplicateCategory(caption="Near Duplicates", groups=[], total_groups=0, total_images=0),
            )

        id_to_url = {img["id"]: img["image_url"] for img in images}

        # ── L1 — MD5 (Exact Duplicates) ──────────────────────────────
        exact_pairs: Dict[Tuple[str, str], set] = defaultdict(set)

        def record_exact(id_a: str, id_b: str, layer: str):
            key = (min(id_a, id_b), max(id_a, id_b))
            exact_pairs[key].add(layer)

        self._detect_md5(images, record_exact)
        self._log_layer_matches(exact_pairs, "L1_MD5", id_to_url)

        # Build exact-duplicate groups via Union-Find
        exact_uf = _UnionFind()
        exact_image_ids: Set[str] = set()
        for (a, b) in exact_pairs:
            exact_uf.union(a, b)
            exact_image_ids.add(a)
            exact_image_ids.add(b)

        exact_groups_map: Dict[str, List[str]] = defaultdict(list)
        for img_id in exact_image_ids:
            exact_groups_map[exact_uf.find(img_id)].append(img_id)

        exact_groups: List[DuplicateGroup] = []
        for gid, (_, members) in enumerate(exact_groups_map.items(), 1):
            exact_groups.append(
                DuplicateGroup(
                    group_id=gid,
                    detection_layers=["L1_MD5"],
                    images=[DuplicateImage(image_id=mid, image_url=id_to_url[mid]) for mid in members],
                )
            )

        # ── Exclude L1 images from L2/L3/L4 ──────────────────────────
        remaining_images = [img for img in images if img["id"] not in exact_image_ids]
        self.logger.info(
            f"L1 matched {len(exact_image_ids)} images. "
            f"{len(remaining_images)} images remaining for near-duplicate search."
        )

        # ── L2 + L3 + L4 — Near Duplicates ───────────────────────────
        near_uf = _UnionFind()
        near_pairs: Dict[Tuple[str, str], set] = defaultdict(set)

        def record_near(id_a: str, id_b: str, layer: str):
            key = (min(id_a, id_b), max(id_a, id_b))
            near_uf.union(id_a, id_b)
            near_pairs[key].add(layer)

        # L2 — pHash
        self._detect_phash(remaining_images, record_near)
        self._log_layer_matches(near_pairs, "L2_PHASH", id_to_url)

        # L3 — DINOv2
        self._detect_embedding(
            remaining_images,
            embedding_key="image_embeddings_efficientnetb0",
            threshold=duplicate_threshold,
            layer_tag="L3_DINOV2",
            record_pair=record_near,
        )
        self._log_layer_matches(near_pairs, "L3_DINOV2", id_to_url)

        # L4 — CLIP
        # self._detect_embedding(
        #     remaining_images,
        #     embedding_key="image_embeddings",
        #     threshold=0.87,
        #     layer_tag="L4_CLIP",
        #     record_pair=record_near,
        # )
        # self._log_layer_matches(near_pairs, "L4_CLIP", id_to_url)

        # Build near-duplicate groups
        near_image_ids: Set[str] = set()
        for (a, b) in near_pairs:
            near_image_ids.add(a)
            near_image_ids.add(b)

        near_groups_map: Dict[str, List[str]] = defaultdict(list)
        for img_id in near_image_ids:
            near_groups_map[near_uf.find(img_id)].append(img_id)

        near_groups: List[DuplicateGroup] = []
        for gid, (_, members) in enumerate(near_groups_map.items(), 1):
            layers: set = set()
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    key = (min(a, b), max(a, b))
                    layers.update(near_pairs.get(key, set()))
            near_groups.append(
                DuplicateGroup(
                    group_id=gid,
                    detection_layers=sorted(layers),
                    images=[DuplicateImage(image_id=mid, image_url=id_to_url[mid]) for mid in members],
                )
            )

        # ── Log final results ─────────────────────────────────────────
        exact_img_count = sum(len(g.images) for g in exact_groups)
        near_img_count = sum(len(g.images) for g in near_groups)
        self.logger.info(f"=== Exact Duplicates: {len(exact_groups)} group(s), {exact_img_count} images ===")
        for g in exact_groups:
            self.logger.info(f"  Group {g.group_id}:")
            for img in g.images:
                self.logger.info(f"    - ID: {img.image_id}  |  URL: {img.image_url}")
        self.logger.info(f"=== Near Duplicates: {len(near_groups)} group(s), {near_img_count} images ===")
        for g in near_groups:
            self.logger.info(f"  Group {g.group_id} | Layers: {g.detection_layers}:")
            for img in g.images:
                self.logger.info(f"    - ID: {img.image_id}  |  URL: {img.image_url}")

        return DuplicateDetectionResponse(
            project_id=project_id,
            exact_duplicates=DuplicateCategory(
                caption="Exact Duplicates",
                groups=exact_groups,
                total_groups=len(exact_groups),
                total_images=exact_img_count,
            ),
            near_duplicates=DuplicateCategory(
                caption="Near Duplicates",
                groups=near_groups,
                total_groups=len(near_groups),
                total_images=near_img_count,
            ),
        )

    # ── Logging helper ────────────────────────────────────────────────

    def _log_layer_matches(self, pair_layers: Dict, layer_tag: str, id_to_url: Dict[str, str]):
        """Log the duplicate groups found by a specific detection layer."""
        layer_pairs = [(a, b) for (a, b), layers in pair_layers.items() if layer_tag in layers]
        if not layer_pairs:
            self.logger.info(f"[{layer_tag}] No duplicates found")
            return

        temp_uf = _UnionFind()
        for a, b in layer_pairs:
            temp_uf.union(a, b)

        all_ids: set = set()
        for a, b in layer_pairs:
            all_ids.add(a)
            all_ids.add(b)

        groups: Dict[str, List[str]] = defaultdict(list)
        for img_id in all_ids:
            groups[temp_uf.find(img_id)].append(img_id)

        self.logger.info(f"[{layer_tag}] Found {len(groups)} group(s) from {len(layer_pairs)} pair(s)")
        for idx, (_, members) in enumerate(groups.items(), 1):
            self.logger.info(f"  Group {idx}:")
            for mid in members:
                self.logger.info(f"    - ID: {mid}  |  URL: {id_to_url.get(mid, 'N/A')}")

    # ── Layer helpers ────────────────────────────────────────────────

    def _detect_md5(self, images: List[dict], record_pair):
        hash_groups: Dict[str, List[str]] = defaultdict(list)
        for img in images:
            h = img.get("md5_hash")
            if h:
                hash_groups[h].append(img["id"])
        for ids in hash_groups.values():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    record_pair(ids[i], ids[j], "L1_MD5")

    def _detect_phash(self, images: List[dict], record_pair):
        valid = [(img["id"], imagehash.hex_to_hash(img["phash"]))
                 for img in images if img.get("phash")]
        for i in range(len(valid)):
            for j in range(i + 1, len(valid)):
                distance = valid[i][1] - valid[j][1]  # Hamming distance
                if distance < 10:
                    record_pair(valid[i][0], valid[j][0], "L2_PHASH")

    def _detect_embedding(self, images: List[dict], embedding_key: str,
                          threshold: float, layer_tag: str, record_pair):
        valid_items = []
        embeddings_list = []
        for img in images:
            emb = img.get(embedding_key)
            if not emb:
                continue
            if isinstance(emb, str):
                emb = [float(x.strip()) for x in emb.strip("[]").split(",")]
            if isinstance(emb, list):
                emb = np.array(emb, dtype=np.float32)
            else:
                continue
            valid_items.append(img)
            embeddings_list.append(emb)

        if len(valid_items) < 2:
            return

        matrix = np.vstack(embeddings_list).astype("float32")
        dim = matrix.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(matrix)

        k = min(len(valid_items), 50)  # search top-k neighbours
        distances, indices = index.search(matrix, k)

        for i in range(len(valid_items)):
            for rank in range(1, k):  # skip self at rank 0
                j = int(indices[i][rank])
                if j < 0:
                    break
                sim = float(distances[i][rank])
                if sim >= threshold:
                    record_pair(valid_items[i]["id"], valid_items[j]["id"], layer_tag)
