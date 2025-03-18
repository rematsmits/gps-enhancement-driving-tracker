import logging

from functions.safe_datetime import safe_datetime
from functions.js_date_format import format_time_for_js

from services.interpolator import interpolate_track
from services.points_smoother import ekf_smooth_track, smooth_track
from services.track_chunks_processor import chunk_track, connect_processed_chunks
from services.valhalla_adapter import process_chunk_with_valhalla
from services.gpx_processor import build_gpx_from_coords, parse_gpx_file
from services.speed_processor import calculate_speeds, refine_points

# Configure logging
logger = logging.getLogger(__name__)

def prepare_track_for_template(track_points):
    """Convert track points to a serializable format for the template"""
    if not track_points:
        return []  # Return empty array instead of None
        
    result = []
    for pt in track_points:
        point = {
            'lat': pt.get('lat', 0),
            'lon': pt.get('lon', 0)
        }
        
        # Format time as ISO string for JavaScript compatibility if it exists
        if pt.get('time'):
            try:
                point['time'] = format_time_for_js(pt['time'])
            except Exception:
                pass
        
        # Add speed information if available
        if pt.get('speed') is not None:
            try:
                # Round speed to 1 decimal place to save space
                point['speed'] = round(float(pt.get('speed')), 1)
            except Exception as e:
                logger.warning(f"Error formatting speed: {e}")
                pass
                
        result.append(point)
        
    return result

def process_track(track):
    """
    Process a track with smoothing, interpolation, map matching, and speed calculation
    Ensures all points have speed data for display in the frontend.
    
    Args:
        track: List of track points as dicts with lat, lon, time
    
    Returns:
        List of processed track coordinates as dicts with lat, lon, time, speed
    """
    try:
        # Step 1: Calculate initial speeds from raw GPS data
        track_with_speeds = calculate_speeds(track)
        logger.info(f"Initial speed calculation: {len(track_with_speeds)} points")
        
        # Log speed range for debugging
        speeds = [p.get('speed') for p in track_with_speeds if p.get('speed') is not None]
        if speeds:
            logger.info(f"Speed range: {min(speeds):.1f} to {max(speeds):.1f} km/h, avg: {sum(speeds)/len(speeds):.1f} km/h")
        
        # Step 2: Use moving average filter for position smoothing
        smoothed = smooth_track(track_with_speeds)
        logger.info(f"Moving average smoothing applied: {len(smoothed)} points")
        
        # Free memory
        del track_with_speeds
        gc.collect()
        
        # Step 3: Calculate track length for adaptive interpolation spacing
        track_length_km = 0
        try:
            track_length_km = sum(
                haversine(smoothed[i]['lat'], smoothed[i]['lon'], 
                       smoothed[i+1]['lat'], smoothed[i+1]['lon'])
                for i in range(len(smoothed) - 1)
            )
            logger.info(f"Track length: {track_length_km:.2f} km")
        except Exception as e:
            logger.warning(f"Error calculating track length: {e}")
        
        # Adjust interpolation spacing based on track length
        # - Short tracks (<10km): 5m spacing for detailed view
        # - Medium tracks (10-50km): 10m spacing
        # - Long tracks (>50km): 15-20m spacing to limit point count
        if track_length_km < 10:
            meter_spacing = 5
        elif track_length_km < 50:
            meter_spacing = 10
        else:
            meter_spacing = 20
        
        # Step 4: Use enhanced interpolation that ensures all points have speed data
        processed_points = interpolate_track(smoothed, meter_per_point=meter_spacing)
        logger.info(f"Interpolation with speed data complete: {len(processed_points)} points")
        
        # Free memory
        del smoothed
        gc.collect()
        
        # Step 5: Split into chunks and process with Valhalla
        chunks = chunk_track(processed_points)
        logger.info(f"Track split into {len(chunks)} chunks for processing")
        
        # Free memory
        del processed_points
        gc.collect()
        
        processed_chunks = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} with {len(chunk)} points")
            matched_coords = process_chunk_with_valhalla(chunk)

            if matched_coords and len(matched_coords) >= 5:
                logger.info(f"Successfully processed chunk {i+1} with {len(matched_coords)} points")
                # Convert tuples to dictionaries if necessary
                if matched_coords and isinstance(matched_coords[0], tuple):
                    matched_coords = [{'lat': lat, 'lon': lon} for lat, lon in matched_coords]
                processed_chunks.append(matched_coords)
            else:
                logger.warning(f"Failed to process chunk {i+1}, will try again with smaller pieces")
                
                # If a chunk fails, try to process it as smaller sub-chunks
                if len(chunk) > 1000:
                    sub_chunk_size = min(1000, len(chunk) // 2)
                    sub_overlap = sub_chunk_size // 5
                    sub_chunks = chunk_track(chunk, sub_chunk_size, sub_overlap)
                    
                    for sub_chunk in sub_chunks:
                        sub_matched = process_chunk_with_valhalla(sub_chunk)
                        if sub_matched and len(sub_matched) >= 5:
                            # Convert tuples to dictionaries if necessary
                            if sub_matched and isinstance(sub_matched[0], tuple):
                                sub_matched = [{'lat': lat, 'lon': lon} for lat, lon in sub_matched]
                            processed_chunks.append(sub_matched)
        
        # Step 6: Connect the processed chunks
        matched_track = connect_processed_chunks(processed_chunks)
        logger.info(f"Connected processed chunks: {len(matched_track)} points")
        
        # Free memory
        del processed_chunks
        gc.collect()
        
        # Convert tuples to dictionaries if necessary
        if matched_track and isinstance(matched_track[0], tuple):
            matched_track = [{'lat': lat, 'lon': lon} for lat, lon in matched_track]
        
        # Step 7: Ensure all points have time and speed fields
        for point in matched_track:
            if 'time' not in point:
                point['time'] = None  # Will be filled in build_gpx_from_coords

        # Step 8: Recalculate speeds for the final track
        # This ensures speed data is accurate after map matching
        final_coords = calculate_speeds(matched_track)
        logger.info(f"Final speed calculation complete: {len(final_coords)} points")
        
        # Check and log speed data coverage
        points_with_speed = sum(1 for p in final_coords if p.get('speed') is not None)
        logger.info(f"Speed data coverage: {points_with_speed}/{len(final_coords)} points ({points_with_speed/len(final_coords)*100:.1f}%)")
        
        # Free memory
        del matched_track
        gc.collect()
        
        return final_coords
    
    except Exception as e:
        logger.error(f"Error in track processing: {str(e)}")
        # logger.error(traceback.format_exc())
        # Return original track if processing fails
        return track

def process_gpx_workflow(gpx_contents, return_raw_data=False):
    """
    Complete workflow for processing a GPX file
    Ensures speed data is available for frontend display
    
    Args:
        gpx_contents: String containing GPX file contents
        return_raw_data: Boolean, if True will return raw_points and processed_coords
        
    Returns:
        tuple: (success, message, gpx_xml, track_points, track_data_for_template, raw_points, processed_coords)
            - success: Boolean indicating if processing was successful
            - message: Status message for the user
            - gpx_xml: Generated GPX XML string for download (None if return_raw_data=True)
            - track_points: List of processed track points
            - track_data_for_template: Formatted track data for the template
            - raw_points: Raw parsed points (only if return_raw_data=True)
            - processed_coords: Processed coordinates (only if return_raw_data=True)
    """
    try:
        # Parse the GPX file
        raw_points = parse_gpx_file(gpx_contents, safe_datetime)
        
        if not raw_points:
            if return_raw_data:
                return False, "No track points found in GPX.", None, None, [], None, None
            else:
                return False, "No track points found in GPX.", None, None, [], None
        
        # Process the track with speed data
        processed_coords = process_track(raw_points)
        
        if not processed_coords:
            if return_raw_data:
                return False, "Processing failed. Try again.", None, None, [], None, None
            else:
                return False, "Processing failed. Try again.", None, None, [], None
        
        # Generate GPX XML only if not returning raw data
        gpx_xml = None
        if not return_raw_data:
            # Build GPX from processed coordinates
            gpx_xml, track_points = build_gpx_from_coords(
                processed_coords, raw_points
            )
        else:
            # Just get track points without building the full GPX XML
            _, track_points = build_gpx_from_coords(
                processed_coords, raw_points
            )
        
        # Additional speed refinement
        # Find indices with reliable speed data
        known_speed_indices = []
        for i, pt in enumerate(track_points):
            # If point already has speed, consider it reliable
            if pt.get('speed') is not None:
                known_speed_indices.append(i)
                
        # If we have some speeds but not for all points, refine them
        if known_speed_indices and len(known_speed_indices) < len(track_points):
            # Use every point with time as an anchor
            known_time_indices = [i for i, pt in enumerate(track_points) if pt.get('time')]
            
            # Refine the track with advanced time and speed interpolation
            if known_time_indices:
                track_points = refine_points(
                    track_points, 
                    known_time_indices, 
                    known_speed_indices,
                    chunk_size=4
                )
        
        # Final check to ensure ALL points have speed data (important for frontend)
        for i, point in enumerate(track_points):
            if 'speed' not in point or point['speed'] is None:
                # Use a default if no speed data available
                point['speed'] = 20  # Default 20 km/h
                
        # Prepare data for template
        track_data = prepare_track_for_template(track_points)
        
        # Log speed data for debugging
        speeds = [p.get('speed') for p in track_data if p.get('speed') is not None]
        if speeds:
            logger.info(f"Final speed range: {min(speeds):.1f} to {max(speeds):.1f} km/h, avg: {sum(speeds)/len(speeds):.1f} km/h")
            logger.info(f"Speed data coverage in final output: {len(speeds)}/{len(track_data)} points ({len(speeds)/len(track_data)*100:.1f}%)")
        
        success_message = f"Track processed successfully with {len(track_points)} points! Speed data calculated for display."
        
        # Return all needed data, including raw data if requested
        if return_raw_data:
            return True, success_message, gpx_xml, track_points, track_data, raw_points, processed_coords
        else:
            return True, success_message, gpx_xml, track_points, track_data, None
        
    except Exception as e:
        logger.error(f"Error in GPX processing workflow: {str(e)}", exc_info=True)
        if return_raw_data:
            return False, f"Error processing file: {str(e)}", None, None, [], None, None
        else:
            return False, f"Error processing file: {str(e)}", None, None, [], None