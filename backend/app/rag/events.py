STREAM_TYPE_RAG_INDEX = "rag_index"

# One event per (document | seed file) indexing batch — see commands.py.
RAG_CHUNKS_INDEXED = "RagChunksIndexed"

# The three separately-scoped corpora (PRD §6.4).
SCOPE_PATIENT_NOTES = "patient_notes"
SCOPE_CLINICAL_GUIDELINES = "clinical_guidelines"
SCOPE_PATIENT_EDUCATION = "patient_education"

SOURCE_TYPE_DOCUMENT = "document"
SOURCE_TYPE_GUIDELINE_SEED = "guideline_seed"
SOURCE_TYPE_EDUCATION_SEED = "education_seed"

CHUNKER_VERSION = "v1"
EMBEDDING_MODEL = "gemini-embedding-001"
