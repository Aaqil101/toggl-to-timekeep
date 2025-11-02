# Built-In Modules
import json
import re
from datetime import datetime, timedelta

# External Modules
import pdfplumber


def parse_toggl_pdf(pdf_path, start_date_str="2024-11-05", debug=False):
    """
    Parses a Toggl Track detailed report PDF and returns a list of entries
    formatted for Obsidian Timekeep.

    Args:
        pdf_path: Path to the Toggl PDF report
        start_date_str: Starting date in YYYY-MM-DD format
        debug: If True, prints extracted text for debugging
    """
    entries = []
    current_date = datetime.strptime(start_date_str, "%Y-%m-%d")

    # Open PDF and read text from all pages
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # Remove null bytes that sometimes appear in PDF text extraction
    full_text = full_text.replace("\x00", "")

    if debug:
        print("=== EXTRACTED TEXT (first 1000 chars) ===")
        print(repr(full_text[:1000]))
        print("\n=== PARSING ENTRIES ===\n")

    # Split by the "Alltimeentriesfromto" marker to get daily sections
    sections = re.split(r"Alltime\s*entries\s*from.*?to", full_text)

    if debug:
        print(f"Found {len(sections)} sections\n")

    # Generic pattern to match any task entry
    # Format: DESCRIPTION (any text) + DURATION + TIME_START TIME_END
    pattern = re.compile(
        r"^(.+?)\s+"  # Description (non-greedy, any text until duration)
        r"(\d{6}|\d+:\d+:\d+|\d+:\d+\s+min|\d+\s+min|\d+\s+sec)\s+"  # Duration
        r"(\d{4})\s+(\d{4})\s*$",  # Start and end times
        re.MULTILINE,
    )

    section_num = 0
    for section in sections:
        if not section.strip():
            continue

        section_num += 1
        section_entries = []

        # Skip if section doesn't have DESCRIPTION header (not a real data section)
        if "DESCRIPTION" not in section and "TIME" not in section:
            if debug:
                print(f"Skipping section {section_num} (no data header)\n")
            continue

        # Extract task entries from this section
        lines = section.split("\n")
        for i, line in enumerate(lines):
            # Look for pattern: task name followed by duration and times on same or next line
            # Match any line that ends with duration and times
            time_match = re.search(
                r"(.+?)\s+"
                r"(?:\d{6}|\d+:\d+:\d+|\d+:\d+\s+min|\d+\s+min|\d+\s+sec)\s+"
                r"(\d{4})\s+(\d{4})\s*$",
                line,
            )

            if time_match:
                # Extract the task name (everything before duration)
                full_line = line
                # Get task name by removing the duration and times at the end
                task_match = re.match(
                    r"(.+?)\s+(?:\d{6}|\d+:\d+:\d+|\d+:\d+\s+min|\d+\s+min|\d+\s+sec)\s+\d{4}\s+\d{4}\s*$",
                    line,
                )
                if task_match:
                    task_name = task_match.group(1).strip()
                    start_time_str = time_match.group(2)
                    end_time_str = time_match.group(3)

                    start_hour = int(start_time_str[:2])
                    start_min = int(start_time_str[2:])
                    end_hour = int(end_time_str[:2])
                    end_min = int(end_time_str[2:])

                    # Create datetime objects
                    start_dt = current_date.replace(
                        hour=start_hour, minute=start_min, second=0
                    )
                    end_dt = current_date.replace(
                        hour=end_hour, minute=end_min, second=0
                    )

                    # Handle overnight sessions
                    if end_dt < start_dt:
                        end_dt += timedelta(days=1)

                    # If start and end are the same, it's a sub-minute entry
                    if end_dt == start_dt:
                        end_dt += timedelta(minutes=1)
                        if debug:
                            print(f"Sub-minute entry: {task_name}")

                    section_entries.append((task_name, start_dt, end_dt))

        # Add all entries from this section
        if section_entries:
            if debug:
                print(f"Section {section_num}: {len(section_entries)} entries")

            # Remove duplicate entries (same name, start, and end time)
            seen = set()
            unique_entries = []
            for task_name, start_dt, end_dt in section_entries:
                key = (task_name, start_dt, end_dt)
                if key not in seen:
                    seen.add(key)
                    unique_entries.append((task_name, start_dt, end_dt))
                elif debug:
                    print(
                        f"Removing duplicate: {task_name} {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                    )

            for task_name, start_dt, end_dt in unique_entries:
                if debug:
                    print(
                        f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}: {task_name}"
                    )

                # Format as ISO 8601 with milliseconds and Z suffix (UTC)
                start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:00.000Z")
                end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:00.000Z")

                entries.append(
                    {
                        "name": task_name,
                        "startTime": start_iso,
                        "endTime": end_iso,
                        "subEntries": None,
                    }
                )

            # Move to next day after processing each section
            current_date += timedelta(days=1)
            if debug:
                print(f"\n--- Day change to {current_date.strftime('%Y-%m-%d')} ---\n")

    return entries


def make_timekeep_block(entries):
    """
    Converts parsed entries into a Timekeep markdown block.
    """
    data = {"entries": entries}
    json_str = json.dumps(data, separators=(",", ":"))
    return f"```timekeep\n{json_str}\n```"


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Convert Toggl PDF to Timekeep JSON block."
    )
    parser.add_argument("pdf", help="Path to Toggl detailed report PDF")
    parser.add_argument(
        "-d",
        "--start-date",
        help="Starting date (YYYY-MM-DD)",
        default=None,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file (optional, .json). If not specified, uses PDF filename",
        default=None,
    )
    parser.add_argument("--debug", action="store_true", help="Print debug information")
    args = parser.parse_args()

    # Extract date from filename
    if args.start_date is None:
        date_match = re.search(r"from_(\d{4})_(\d{2})_(\d{2})", args.pdf)
        if date_match:
            args.start_date = (
                f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
            )
        else:
            args.start_date = input("Enter start date (YYYY-MM-DD): ")

    # Generate output filename from PDF filename if not specified
    if args.output is None:
        pdf_path = Path(args.pdf)
        args.output = pdf_path.stem + ".json"

    entries = parse_toggl_pdf(args.pdf, args.start_date, debug=args.debug)

    # Write JSON file
    data = {"entries": entries}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Also write a human-readable list
    readable_output = args.output.replace(".json", "_readable.txt")
    with open(readable_output, "w", encoding="utf-8") as f:
        f.write(f"Total entries: {len(entries)}\n")
        f.write(f"Start date: {args.start_date}\n\n")
        for i, entry in enumerate(entries, 1):
            start = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(entry["endTime"].replace("Z", "+00:00"))
            duration_min = (end - start).total_seconds() / 60
            f.write(
                f"{i:3d}. {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%H:%M')} | {entry['name']} ({duration_min:.0f} min)\n"
            )

    print(f"\n{'='*50}")
    print(f"✅ JSON saved to {args.output}")
    print(f"✅ Readable list saved to {readable_output}")
    print(f"   Total entries: {len(entries)}")
    print(f"   Start date: {args.start_date}")

    if len(entries) > 0:
        first_entry = entries[0]
        last_entry = entries[-1]
        print(f"   First entry: {first_entry['startTime']}")
        print(f"   Last entry:  {last_entry['endTime']}")

        # Calculate total time
        total_minutes = 0
        for entry in entries:
            start = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(entry["endTime"].replace("Z", "+00:00"))
            total_minutes += (end - start).total_seconds() / 60

        hours = int(total_minutes // 60)
        minutes = int(total_minutes % 60)
        print(f"   Total time: {hours}h {minutes}m")
    print(f"{'='*50}")
