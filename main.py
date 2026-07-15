import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta


def extract_date_range(csv_filename):
    """Extract start and end dates from the CSV header line"""
    with open(csv_filename, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        # Pattern: "All time entries from YYYY-MM-DD to YYYY-MM-DD"
        match = re.search(
            r"from (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", first_line
        )
        if match:
            start_date = match.group(1)
            end_date = match.group(2)
            return start_date, end_date
        else:
            raise ValueError("Could not find date range in CSV header")


def parse_duration(duration_str):
    """Convert duration string (HH:MM:SS) to timedelta object"""
    hours, minutes, seconds = map(int, duration_str.split(":"))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_time_range(time_str, base_date):
    """Parse time range like '20:26 - 21:53' and return start/end datetimes"""
    start_time_str, end_time_str = time_str.split(" - ")

    # Parse start time
    start_hour, start_minute = map(int, start_time_str.split(":"))
    start_dt = base_date.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )

    # Parse end time
    end_hour, end_minute = map(int, end_time_str.split(":"))
    end_dt = base_date.replace(
        hour=end_hour, minute=end_minute, second=0, microsecond=0
    )

    # Handle midnight crossing (e.g., 23:32 - 00:01)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)

    return start_dt, end_dt


def process_csv_file(csv_filename, output_filename=None):
    """
    Process a single CSV file and convert to JSON

    Returns:
        tuple: (success: bool, output_file: str, entry_count: int, error: str)
    """
    try:
        # If no output filename specified, use input filename with .json extension
        if output_filename is None:
            base_name = os.path.splitext(csv_filename)[0]
            output_filename = f"{base_name}.json"

        result = csv_to_timekeep_json(csv_filename, output_filename)
        return (True, output_filename, len(result["entries"]), None)
    except Exception as e:
        return (False, output_filename, 0, str(e))


def csv_to_timekeep_json(csv_filename, output_filename=None):
    """
    Convert Timekeep CSV export to JSON format

    Args:
        csv_filename: Input CSV file path
        output_filename: Output JSON file path (defaults to input filename with .json extension)
    """
    # If no output filename specified, use input filename with .json extension
    if output_filename is None:
        base_name = os.path.splitext(csv_filename)[0]
        output_filename = f"{base_name}.json"

    # Extract date range from header
    start_date_str, end_date_str = extract_date_range(csv_filename)
    base_date = datetime.fromisoformat(start_date_str)

    entries = []
    current_date = base_date

    with open(csv_filename, "r", encoding="utf-8") as f:
        # Skip the first line (date range header)
        f.readline()
        reader = csv.DictReader(f)

        previous_end_time = None

        for i, row in enumerate(reader):
            description = row["DESCRIPTION"]
            duration_str = row["DURATION"]
            time_range = row["TIME"]

            # Parse the time range to get start time
            start_dt, _ = parse_time_range(time_range, current_date)

            # If this session starts before the previous one ended, we've moved to a new day
            if previous_end_time and start_dt < previous_end_time:
                current_date += timedelta(days=1)
                start_dt, _ = parse_time_range(time_range, current_date)

            # Use the actual DURATION from CSV to calculate end time
            duration = parse_duration(duration_str)
            end_dt = start_dt + duration

            previous_end_time = end_dt

            # Create entry in Timekeep format
            entry = {
                "name": description,
                "startTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "endTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "subEntries": None,
            }
            entries.append(entry)

    # Create final JSON structure
    timekeep_data = {"entries": entries}

    # Write to file
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(timekeep_data, f, indent=2)

    return timekeep_data


# Command line interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_csv_file_or_folder> [output_json_file]")
        print("\nExamples:")
        print("  Single file:")
        print("    python main.py test_report.csv")
        print("    python main.py test_report.csv output.json")
        print("\n  Folder (processes all CSV files):")
        print("    python main.py ./csv_folder")
        print("    python main.py C:\\Users\\Documents\\reports")
        sys.exit(1)

    input_path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    # Check if input is a directory
    if os.path.isdir(input_path):
        # Process all CSV files in the directory
        csv_files = glob.glob(os.path.join(input_path, "*.csv"))

        if not csv_files:
            print(f"Error: No CSV files found in '{input_path}'")
            sys.exit(1)

        print(f"Found {len(csv_files)} CSV file(s) in '{input_path}'\n")

        successful = 0
        failed = 0

        for csv_file in csv_files:
            print(f"Processing: {os.path.basename(csv_file)}")
            success, output, count, error = process_csv_file(csv_file)

            if success:
                print(f"  ✓ Success: {count} entries -> {os.path.basename(output)}")
                successful += 1
            else:
                print(f"  ✗ Failed: {error}")
                failed += 1
            print()

        print(f"Summary: {successful} successful, {failed} failed")

    elif os.path.isfile(input_path):
        # Process single file
        if not input_path.lower().endswith(".csv"):
            print(f"Error: '{input_path}' is not a CSV file")
            sys.exit(1)

        print(f"Processing: {input_path}")
        success, output, count, error = process_csv_file(input_path, output_file)

        if success:
            print(f"\n✓ Conversion successful!")
            print(f"  Input:  {input_path}")
            print(f"  Output: {output}")
            print(f"  Total entries: {count}")
        else:
            print(f"\n✗ Error: {error}")
            sys.exit(1)
    else:
        print(f"Error: '{input_path}' not found")
        sys.exit(1)
