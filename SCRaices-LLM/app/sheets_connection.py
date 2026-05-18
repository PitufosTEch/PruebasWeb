import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from config import SPREADSHEET_ID, CREDENTIALS_PATH

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]

class SheetsConnection:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self._connect()

    def _connect(self):
        """Establish connection to Google Sheets (read-only)"""
        credentials = Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=SCOPES
        )
        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(SPREADSHEET_ID)

    def get_sheet_names(self) -> list:
        """Get list of all sheet/tab names"""
        return [sheet.title for sheet in self.spreadsheet.worksheets()]

    def get_sheet_data(self, sheet_name: str) -> pd.DataFrame:
        """Read a sheet and return as DataFrame. Handles duplicate column names."""
        worksheet = self.spreadsheet.worksheet(sheet_name)

        # Try normal method first
        try:
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            # If duplicate columns error, handle manually
            if 'duplicates' in str(e).lower():
                all_values = worksheet.get_all_values()
                if not all_values:
                    return pd.DataFrame()

                headers = all_values[0]

                # Rename duplicates by adding _1, _2, etc.
                seen = {}
                new_headers = []
                for h in headers:
                    if h in seen:
                        seen[h] += 1
                        new_headers.append(f'{h}_{seen[h]}')
                    else:
                        seen[h] = 0
                        new_headers.append(h)

                return pd.DataFrame(all_values[1:], columns=new_headers)
            else:
                raise

    def get_sheet_preview(self, sheet_name: str, rows: int = 5) -> pd.DataFrame:
        """Get preview of a sheet (first N rows)"""
        df = self.get_sheet_data(sheet_name)
        return df.head(rows)


if __name__ == "__main__":
    # Test connection
    conn = SheetsConnection()
    sheets = conn.get_sheet_names()
    print(f"Found {len(sheets)} sheets:")
    for name in sheets[:10]:
        print(f"  - {name}")
