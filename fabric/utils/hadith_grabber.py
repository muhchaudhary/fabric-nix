import requests
import random

API_URL = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"

main_books = [
    ("eng-bukhari", 7563),
    ("eng-muslim", 7563),
    ("eng-nasai", 5758),
    ("eng-abudawud", 5274),
    ("eng-ibnmajah", 4341),
    ("eng-tirmidhi", 3956),
]


class Hadith:
    def __init__(self) -> None:
        self.hadith_json: dict = {}
        self.book_name: str = ""
        self.book_number: int = -1
        self.section_name: str = ""
        self.hadith_text: str = ""
        self.hadith_number: int = -1
        self.arabic_number: int = -1

    def get_random_hadith(self):
        book_number = random.randint(1, len(main_books) - 1)
        hadith_number = random.randint(1, main_books[book_number][1])
        try:
            self.hadith_json = requests.get(
                f"{API_URL}/editions/{main_books[book_number][0]}/{hadith_number}.json"
            ).json()
        except Exception as e:
            return
        self.book_name = self.hadith_json["metadata"]["name"]
        self.section_name = list(self.hadith_json["metadata"]["section"].values())[0]
        self.hadith_text = self.hadith_json["hadiths"][0]["text"]
        self.book_number, self.hadith_number = self.hadith_json["hadiths"][0][
            "reference"
        ].values()
        self.arabic_number = self.hadith_json["hadiths"][0]["arabicnumber"]
