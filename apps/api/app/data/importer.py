import hashlib
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.data.schemas import SyntheticDataset
from app.db.models import ProviderDatasetRecord


def dataset_hash(dataset: SyntheticDataset) -> str:
    return hashlib.sha256(dataset.model_dump_json().encode()).hexdigest()


def load_dataset(path: Path) -> SyntheticDataset:
    if path.stat().st_size > 256 * 1024:
        raise ValueError("Synthetic dataset exceeds 256 KiB")
    return SyntheticDataset.model_validate_json(path.read_bytes())


def import_dataset(session: Session, dataset: SyntheticDataset) -> str:
    if dataset.generated_at > datetime.now(UTC):
        raise ValueError("Future generation timestamp")
    version = dataset_hash(dataset)
    session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": "synthetic:" + dataset.slug},
    )
    existing = session.scalar(
        sa.select(ProviderDatasetRecord).where(
            ProviderDatasetRecord.provider == "synthetic",
            ProviderDatasetRecord.slug == dataset.slug,
            ProviderDatasetRecord.revision == dataset.revision,
        )
    )
    if existing:
        if existing.data_version != version:
            raise ValueError("Revision already exists with different content")
        return version
    active = session.scalar(
        sa.select(ProviderDatasetRecord).where(
            ProviderDatasetRecord.provider == "synthetic",
            ProviderDatasetRecord.slug == dataset.slug,
            ProviderDatasetRecord.active,
        )
    )
    if active:
        previous = SyntheticDataset.model_validate(active.document)
        if dataset.generated_at <= previous.generated_at:
            raise ValueError("New revision must have a later generation timestamp")
        active.active = False
        session.flush()
    session.add(
        ProviderDatasetRecord(
            provider="synthetic",
            slug=dataset.slug,
            revision=dataset.revision,
            data_version=version,
            document=dataset.model_dump(mode="json"),
            active=True,
            imported_at=datetime.now(UTC),
        )
    )
    session.flush()
    return version


def main() -> None:
    import argparse

    from sqlalchemy.exc import SQLAlchemyError

    from app.db.session import get_engine

    parser = argparse.ArgumentParser(description="Validate/import a local synthetic dataset")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.path)
        with Session(get_engine()) as session, session.begin():
            version = import_dataset(session, dataset)
        print(version)
    except (OSError, ValueError, SQLAlchemyError):
        parser.exit(
            1,
            "Synthetic import rejected; active data preserved. "
            "Check schema, revision and database access.\n",
        )


if __name__ == "__main__":
    main()
