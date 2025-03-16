import logging
from services.interpolator import haversine

# Configure logging
logger = logging.getLogger(__name__)

# Split track into chunks that are under Valhalla's point limit
def chunk_track(points, max_chunk_size=12_000, overlap=20):
    """Split track into chunks with overlap for processing with Valhalla"""
    # For very small tracks, don't split
    if len(points) <= max_chunk_size:
        return [points]  # Track is small enough to process in one go

    chunks = []
    start_idx = 0
    
    while start_idx < len(points):
        # Calculate end index for this chunk (including overlap)
        end_idx = min(start_idx + max_chunk_size, len(points))
        
        # Extract chunk
        chunk = points[start_idx:end_idx]
        chunks.append(chunk)
        
        # Move to next chunk start, with overlap for better stitching
        start_idx = end_idx - overlap if end_idx < len(points) else len(points)
    
    return chunks

def connect_processed_chunks(chunks):
    """Connect multiple processed chunks with ultra-simple end-to-end stitching"""
    # Handle empty input
    if not chunks:
        return []
    if len(chunks) == 1:
        return chunks[0]
    
    # Start with the first valid chunk
    connected = chunks[0].copy()
    
    # Simply connect each subsequent chunk end-to-end
    for i in range(1, len(chunks)):
        # Skip empty chunks
        if not chunks[i]:
            continue
            
        # Simple connection strategy
        p1 = connected[-1]  # Last point of current track
        p2 = chunks[i][0]  # First point of next chunk
        
        # Calculate distance between endpoints
        dist = haversine(p1[0], p1[1], p2[0], p2[1])
        
        # Log the connection
        logger.info(f"Connecting chunks {i-1} and {i} (distance: {dist:.1f}m)")
        
        # If endpoints are very close (within 10m), skip the first point of next chunk
        if dist < 10:
            connected.extend(chunks[i][1:])
        # For moderate gaps (10-80m), add a single midpoint to smooth the transition
        elif dist < 80:
            # Add a single midpoint halfway between
            midpoint = (
                (p1[0] + p2[0]) / 2, 
                (p1[1] + p2[1]) / 2
            )
            connected.append(midpoint)
            connected.extend(chunks[i])
        # For all other cases, just append the next chunk directly
        else:
            connected.extend(chunks[i])
    
    return connected
