"""Per-link comment cap with total-pool scaling."""


def comments_per_link(url_count: int) -> int:
    if url_count <= 0:
        raise ValueError("url_count must be >= 1")
    if url_count <= 10:
        return 500
    return 5000 // url_count
