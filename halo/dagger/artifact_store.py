#!/usr/bin/env python3
"""MinIO artifact store — upload/download test results (DAG-NF3).

Uploads to: artifacts/{project}/{spec_id}/
"""

import os


class ArtifactStore:
    """Test artifact upload/download to MinIO via halo.common.minio_client."""

    def __init__(self, minio_client, bucket="halo-artifacts"):
        self.minio = minio_client
        self.bucket = bucket

    def upload_junit(self, project, spec_id, junit_xml, junit_path=None):
        """Upload JUnit XML test results."""
        object_name = f"artifacts/{project}/{spec_id}/junit.xml"
        if junit_path and os.path.isfile(junit_path):
            with open(junit_path, "r") as f:
                junit_xml = f.read()
        self.minio.upload(object_name, junit_xml, content_type="application/xml")
        return object_name

    def upload_coverage(self, project, spec_id, coverage_html_path):
        """Upload coverage HTML report (zipped)."""
        import io
        import zipfile
        object_name = f"artifacts/{project}/{spec_id}/coverage.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(coverage_html_path):
                for fn in files:
                    fpath = os.path.join(root, fn)
                    arcname = os.path.relpath(fpath, coverage_html_path)
                    zf.write(fpath, arcname)
        buf.seek(0)
        self.minio.upsert_upload(object_name, buf, len(buf.getvalue()))
        return object_name

    def upload_playwright_report(self, project, spec_id, report_path):
        """Upload Playwright HTML report (zipped)."""
        import io
        import zipfile
        object_name = f"artifacts/{project}/{spec_id}/playwright-report.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(report_path):
                for fn in files:
                    fpath = os.path.join(root, fn)
                    arcname = os.path.relpath(fpath, report_path)
                    zf.write(fpath, arcname)
        buf.seek(0)
        self.minio.upsert_upload(object_name, buf, len(buf.getvalue()))
        return object_name

    def download(self, project, spec_id, filename):
        """Download an artifact."""
        object_name = f"artifacts/{project}/{spec_id}/{filename}"
        return self.minio.download(object_name)

    def list_artifacts(self, project, spec_id):
        """List all artifacts for a spec."""
        prefix = f"artifacts/{project}/{spec_id}/"
        return [o.object_name for o in self.minio.list_objects(prefix=prefix)]