"""
One-time migration script: copies all points from local Qdrant to Qdrant Cloud.

Run from the project root (not inside Docker) while local Qdrant is still running:
    python migrate_qdrant.py
"""

import httpx

LOCAL_URL = "http://localhost:6333"
LOCAL_API_KEY = "qdrant_key_123"

CLOUD_URL = "https://062ec21b-563b-49b2-ba45-48f1958bf795.eu-west-1-0.aws.cloud.qdrant.io"
CLOUD_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6YmRjYTE2MmYtMmUxOS00NDNiLTgwNGMtZTJiY2Y4MjIyMDc5In0.8ZvAU9lYITtPNeoofC5SHbqfYIFiQ8G2SDUNNM-XL6U"

COLLECTION = "documents"
VECTOR_SIZE = 3072
BATCH_SIZE = 50


def local_headers():
    return {"Content-Type": "application/json", "api-key": LOCAL_API_KEY}


def cloud_headers():
    return {"Content-Type": "application/json", "api-key": CLOUD_API_KEY}


def ensure_cloud_collection(client: httpx.Client):
    resp = client.get(f"{CLOUD_URL}/collections/{COLLECTION}", headers=cloud_headers())
    if resp.status_code == 200:
        count = resp.json()["result"]["points_count"]
        print(f"Cloud collection already exists with {count} points.")
        return

    print("Creating collection on Qdrant Cloud...")
    resp = client.put(
        f"{CLOUD_URL}/collections/{COLLECTION}",
        headers=cloud_headers(),
        json={"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}},
    )
    resp.raise_for_status()
    print("Collection created.")


def scroll_all_local_points(client: httpx.Client):
    points = []
    offset = None
    while True:
        body = {"limit": BATCH_SIZE, "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        resp = client.post(
            f"{LOCAL_URL}/collections/{COLLECTION}/points/scroll",
            headers=local_headers(),
            json=body,
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        batch = result.get("points", [])
        points.extend(batch)
        print(f"  Fetched {len(points)} points so far...")
        offset = result.get("next_page_offset")
        if offset is None:
            break
    return points


def upload_to_cloud(client: httpx.Client, points: list):
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        payload = {
            "points": [
                {"id": p["id"], "vector": p["vector"], "payload": p.get("payload", {})}
                for p in batch
            ]
        }
        resp = client.put(
            f"{CLOUD_URL}/collections/{COLLECTION}/points",
            headers=cloud_headers(),
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        print(f"  Uploaded {min(i + BATCH_SIZE, len(points))}/{len(points)} points...")


def main():
    with httpx.Client(timeout=30.0) as client:
        print("=== Qdrant Migration: Local → Cloud ===\n")

        print("1. Checking local Qdrant...")
        resp = client.get(f"{LOCAL_URL}/collections/{COLLECTION}", headers=local_headers())
        resp.raise_for_status()
        local_count = resp.json()["result"]["points_count"]
        print(f"   Local has {local_count} points.\n")

        print("2. Ensuring collection exists on Qdrant Cloud...")
        ensure_cloud_collection(client)
        print()

        print("3. Reading all points from local Qdrant...")
        points = scroll_all_local_points(client)
        print(f"   Read {len(points)} points total.\n")

        print("4. Uploading to Qdrant Cloud...")
        upload_to_cloud(client, points)
        print()

        print("5. Verifying cloud point count...")
        resp = client.get(f"{CLOUD_URL}/collections/{COLLECTION}", headers=cloud_headers())
        resp.raise_for_status()
        cloud_count = resp.json()["result"]["points_count"]
        print(f"   Cloud now has {cloud_count} points.")

        if cloud_count >= local_count:
            print("\nMigration complete!")
        else:
            print(f"\nWARNING: Expected {local_count} points but cloud has {cloud_count}. Re-run to retry.")


if __name__ == "__main__":
    main()
