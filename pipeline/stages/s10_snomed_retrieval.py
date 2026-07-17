"""
Stage 10: SNOMED Candidate Retrieval - Ontology Mapping

Maps extracted entities to SNOMED CT codes using AWS Comprehend Medical.
"""

import os
import re
from typing import Dict, List, Optional, Tuple

from ..base import PipelineStage, StageResult, PipelineContext, StageStatus, StageRegistry


@StageRegistry.register
class SNOMEDRetrievalStage(PipelineStage):
    """
    SNOMED Retrieval Stage - Map entities to SNOMED CT.

    Uses AWS Comprehend Medical InferSNOMEDCT to map entities.
    Handles chunking for large texts.

    Outputs:
    - snomed_mappings: List of entity-to-SNOMED mappings
    - mapping_confidence: Overall mapping quality
    """

    # Category mapping for Comprehend Medical concepts
    CATEGORY_MAP = {
        "MEDICAL_CONDITION": "diagnoses",
        "DX_NAME": "diagnoses",
        "DIAGNOSIS": "diagnoses",
        "SYMPTOM": "problems",
        "SIGN": "problems",
        "MEDICATION": "medications",
        "GENERIC_NAME": "medications",
        "BRAND_NAME": "medications",
        "TREATMENT_NAME": "treatments",
        "PROCEDURE_NAME": "treatments",
        "TEST_NAME": "investigations",
        "TEST_VALUE": "investigations",
        "ANATOMY": "anatomy",
    }

    @property
    def name(self) -> str:
        return "snomed_retrieval"

    @property
    def description(self) -> str:
        return "Map entities to SNOMED CT codes"

    def get_dependencies(self) -> List[str]:
        return ["ner", "medication_parser", "investigation_parser"]

    def validate_input(self, context: PipelineContext) -> bool:
        return bool(context.get_text())

    def process(self, context: PipelineContext) -> StageResult:
        """Map entities to SNOMED codes."""
        result = StageResult(
            stage_name=self.name,
            status=StageStatus.RUNNING,
            confidence=0.0,
        )

        try:
            text = context.get_text()
            config = context.config

            if not text:
                result.status = StageStatus.SKIPPED
                return result

            # Chunk text for API limits
            chunk_size = config.snomed_chunk_size if config else 4500
            chunks = self._chunk_text(text, chunk_size)

            # Process each chunk
            all_mappings = []
            chunk_confidences = []

            for i, chunk in enumerate(chunks):
                mappings, conf = self._process_chunk(chunk, i)
                all_mappings.extend(mappings)
                chunk_confidences.append(conf)

                result.add_note(f"Chunk {i+1}: {len(mappings)} mappings, conf={conf:.2f}")

            # Categorize mappings
            categorized = self._categorize_mappings(all_mappings)

            # Update context
            context.snomed_mappings = all_mappings

            # Calculate overall confidence
            avg_confidence = sum(chunk_confidences) / len(chunk_confidences) if chunk_confidences else 0.5

            # Build result
            result.status = StageStatus.DONE
            result.confidence = avg_confidence
            result.items_processed = len(all_mappings)
            result.data = {
                "mappings": all_mappings,
                "categorized": categorized,
                "total_mappings": len(all_mappings),
            }
            result.debug_data = {
                "chunks_processed": len(chunks),
                "chunk_confidences": chunk_confidences,
            }

            result.add_note(f"Mapped {len(all_mappings)} entities to SNOMED")

            return result

        except Exception as e:
            result.status = StageStatus.ERROR
            result.error = str(e)
            return result

    def _chunk_text(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks respecting sentence boundaries."""
        chunks = []
        current_chunk = ""

        sentences = re.split(r'(?<=[.!?])\s+', text)

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def _process_chunk(self, text: str, chunk_idx: int) -> Tuple[List[Dict], float]:
        """Process a single text chunk through Comprehend Medical."""
        import boto3
        import sys

        try:
            client = boto3.client(
                "comprehendmedical",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )

            response = client.infer_snomedct(Text=text)

            mappings = []
            confidences = []

            for entity in response.get("Entities", []):
                # Extract SNOMED concepts
                snomed_concepts = entity.get("SNOMEDCTConcepts", [])

                if snomed_concepts:
                    # Take top concept
                    top_concept = snomed_concepts[0]
                    confidence = top_concept.get("Score", 0.5)

                    mapping = {
                        "text": entity.get("Text", ""),
                        "category": entity.get("Category", ""),
                        "type": entity.get("Type", ""),
                        "snomed_code": top_concept.get("Code", ""),
                        "snomed_description": top_concept.get("Description", ""),
                        "confidence": confidence,
                        "start_pos": entity.get("BeginOffset", 0),
                        "end_pos": entity.get("EndOffset", 0),
                        "chunk_idx": chunk_idx,
                        "all_concepts": [
                            {
                                "code": c.get("Code"),
                                "description": c.get("Description"),
                                "score": c.get("Score"),
                            }
                            for c in snomed_concepts[:5]
                        ],
                    }

                    # Check for traits (negation, etc.)
                    traits = entity.get("Traits", [])
                    for trait in traits:
                        if trait.get("Name") == "NEGATION":
                            mapping["negated"] = True
                            mapping["negation_confidence"] = trait.get("Score", 0.5)

                    mappings.append(mapping)
                    confidences.append(confidence)

            avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
            return mappings, avg_conf

        except Exception as e:
            print(f"[WARN] Comprehend Medical failed: {e}", file=sys.stderr)
            return [], 0.3

    def _categorize_mappings(self, mappings: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize mappings into clinical categories."""
        categorized = {
            "diagnoses": [],
            "problems": [],
            "medications": [],
            "treatments": [],
            "investigations": [],
            "anatomy": [],
            "other": [],
        }

        for mapping in mappings:
            category = mapping.get("category", "")
            entity_type = mapping.get("type", "")

            # Determine clinical category
            clinical_cat = self.CATEGORY_MAP.get(category) or self.CATEGORY_MAP.get(entity_type, "other")
            mapping["clinical_category"] = clinical_cat

            if clinical_cat in categorized:
                categorized[clinical_cat].append(mapping)
            else:
                categorized["other"].append(mapping)

        return categorized
