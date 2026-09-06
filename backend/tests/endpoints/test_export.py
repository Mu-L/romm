from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from utils.gamelist_exporter import GamelistExporter
from utils.pegasus_exporter import PegasusExporter

EXPORTERS = {
    "/api/export/gamelist-xml": GamelistExporter,
    "/api/export/pegasus": PegasusExporter,
}

with_endpoint = pytest.mark.parametrize("path", list(EXPORTERS))


@with_endpoint
def test_export_rejects_viewer(client, viewer_access_token: str, path: str):
    # Both endpoints write into the library, so reading ROMs is not enough.
    response = client.post(
        f"{path}?platform_ids=1",
        headers={"Authorization": f"Bearer {viewer_access_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@with_endpoint
def test_export_rejects_anonymous(client, path: str):
    response = client.post(f"{path}?platform_ids=1")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@with_endpoint
def test_export_allows_editor(client, editor_access_token: str, path: str):
    with patch.object(
        EXPORTERS[path],
        "export_platform_to_file",
        new_callable=AsyncMock,
        return_value=True,
    ) as export_mock:
        response = client.post(
            f"{path}?platform_ids=1",
            headers={"Authorization": f"Bearer {editor_access_token}"},
        )

    assert response.status_code == status.HTTP_200_OK
    export_mock.assert_awaited_once()
