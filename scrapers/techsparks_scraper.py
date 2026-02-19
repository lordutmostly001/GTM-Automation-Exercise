"""
TechSparks 2024 Speaker Scraper
================================
Step 1 of the AI/GTM Automation Pipeline

HOW TO RUN:
    pip install selenium beautifulsoup4 pandas requests
    # Also install ChromeDriver matching your Chrome version:
    # https://chromedriver.chromium.org/downloads
    python techsparks_scraper.py

OUTPUT:
    techsparks_speakers_raw.csv  — real scraped speakers
    techsparks_contacts_200.csv  — 200-row master list (real + mock)
"""

import time
import csv
import json
import re
import pandas as pd
from bs4 import BeautifulSoup

# ── Selenium is needed because the speakers section is JS-rendered ──────────
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# ───────────────────────────────────────────────
# PART 1: Scrape real speakers from the event site
# ───────────────────────────────────────────────

def init_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.7632.76 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)



def scrape_techsparks_speakers():
    """Scrapes speaker cards from the TechSparks 2024 website."""
    url = "https://techsparks.yourstory.com/2024"
    driver = init_driver(headless=True)
    speakers = []

    try:
        print(f"[1/4] Loading {url} ...")
        driver.get(url)

        # Wait for speaker cards to load (they're in a grid)
        print("[2/4] Waiting for speaker section to render...")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "img[src*='66b075049c4028af44cdcd07']"))
        )
        time.sleep(3)  # let lazy-loaded images settle

        # Scroll down to trigger any lazy-loading
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Speaker cards share a common pattern: an img followed by name + title text nodes
        # Webflow sites typically wrap each card in a div.w-dyn-item or similar
        # We'll look for the img CDN path unique to speaker photos
        speaker_imgs = soup.find_all("img", src=re.compile(r"66b075049c4028af44cdcd07"))

        print(f"[3/4] Found {len(speaker_imgs)} speaker image elements — extracting data...")

        for img in speaker_imgs:
            # Walk up to the card container, then find sibling text nodes
            card = img.find_parent("div")
            if not card:
                continue

            # Name is usually the first text-heavy element after the image
            texts = [t.get_text(strip=True) for t in card.find_all(["div", "p", "h2", "h3", "h4"])
                     if t.get_text(strip=True)]

            if len(texts) >= 2:
                name = texts[0]
                title_company = texts[1]
            elif len(texts) == 1:
                name = texts[0]
                title_company = ""
            else:
                continue

            # Split "Title, Company" or "Title at Company"
            title, company = parse_title_company(title_company)

            speakers.append({
                "name": name,
                "title": title,
                "company": company,
                "source": "scraped_techsparks2024"
            })

        print(f"[4/4] Scraped {len(speakers)} speakers successfully.")

    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
        print("→ Falling back to known speakers from earlier fetch...")
        speakers = get_known_speakers_fallback()
    finally:
        driver.quit()

    return speakers


def parse_title_company(text):
    """
    Parse strings like:
      'Founder & CEO, Zerodha & Rainmatter'
      'Managing Director, Asia South, NVIDIA'
      'CTO, Microsoft India and South Asia'
    Returns (title, company)
    """
    # Common patterns: last comma-separated segment is often company
    # But "Asia South, NVIDIA" → company=NVIDIA, title includes "Managing Director, Asia South"
    # Strategy: known company names take priority
    known_suffixes = [
        "ISRO", "Zerodha", "Rainmatter", "Microsoft", "NVIDIA", "PhonePe",
        "Groww", "InMobi", "Razorpay", "Snapdeal", "Titan Capital", "upGrad",
        "Swades Foundation", "Elevation Capital", "3one4 Capital", "Prosus Ventures",
        "Open Financial Technologies", "Mensa Brands", "Neysa", "Government of India",
        "Competition Commission of India", "Ola"
    ]
    for co in known_suffixes:
        if co.lower() in text.lower():
            title = text.replace(co, "").strip().rstrip(",").strip()
            return title, co

    # Fallback: split on last comma
    parts = text.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


def get_known_speakers_fallback():
    """
    Hardcoded fallback list of speakers we already extracted from
    the web fetch of techsparks.yourstory.com/2024 earlier in the session.
    Use this if Selenium scraping fails.
    """
    return [
        {"name": "Dr. Sreedhara Panicker Somanath", "title": "Chairman", "company": "Indian Space Research Organisation (ISRO)", "source": "known_fallback"},
        {"name": "Shri Amitabh Kant", "title": "G20 Sherpa", "company": "Government of India", "source": "known_fallback"},
        {"name": "Ronnie Screwvala", "title": "Co-founder", "company": "upGrad & Swades Foundation", "source": "known_fallback"},
        {"name": "Bhavish Aggarwal", "title": "Founder", "company": "Ola", "source": "known_fallback"},
        {"name": "Dr. Rohini Srivathsa", "title": "CTO", "company": "Microsoft India and South Asia", "source": "known_fallback"},
        {"name": "Anil Agrawal", "title": "Member", "company": "Competition Commission of India", "source": "known_fallback"},
        {"name": "Mabel Chacko", "title": "Co-founder & COO", "company": "Open Financial Technologies", "source": "known_fallback"},
        {"name": "Ashutosh Sharma", "title": "Head of Growth Investments, India & Asia", "company": "Prosus Ventures", "source": "known_fallback"},
        {"name": "Mukul Arora", "title": "Co-Managing Partner", "company": "Elevation Capital", "source": "known_fallback"},
        {"name": "Nithin Kamath", "title": "Founder & CEO", "company": "Zerodha & Rainmatter", "source": "known_fallback"},
        {"name": "Naveen Tewari", "title": "Founder & CEO", "company": "InMobi Group", "source": "known_fallback"},
        {"name": "Rahul Chari", "title": "Founder & CTO", "company": "PhonePe", "source": "known_fallback"},
        {"name": "Lalit Keshre", "title": "Co-founder & CEO", "company": "Groww", "source": "known_fallback"},
        {"name": "Kunal Bahl", "title": "Co-founder", "company": "Snapdeal & Titan Capital", "source": "known_fallback"},
        {"name": "Vishal Dhupar", "title": "Managing Director, Asia South", "company": "NVIDIA", "source": "known_fallback"},
        {"name": "Ananth Narayanan", "title": "Founder & CEO", "company": "Mensa Brands", "source": "known_fallback"},
        {"name": "Shashank Kumar", "title": "Managing Director and Co-founder", "company": "Razorpay", "source": "known_fallback"},
        {"name": "Siddarth Pai", "title": "Founding Partner, CFO & ESG Officer", "company": "3one4 Capital", "source": "known_fallback"},
        {"name": "Sharad Sanghi", "title": "Founder", "company": "Neysa", "source": "known_fallback"},
        {"name": "Subbu Iyer", "title": "CEO", "company": "Giggr Technologies", "source": "known_fallback"},
    ]


# ───────────────────────────────────────────────
# PART 2: Enrich with seniority + industry tags
# ───────────────────────────────────────────────

SENIORITY_KEYWORDS = {
    "C-Suite": ["founder", "ceo", "cto", "coo", "cfo", "chief", "chairman", "managing director", "md"],
    "VP/Director": ["vp ", "vice president", "director", "head of", "partner", "sherpa"],
    "Manager/IC": ["manager", "lead", "engineer", "analyst", "associate", "consultant"],
}

INDUSTRY_MAP = {
    "Fintech": ["zerodha", "razorpay", "groww", "phonePe", "open financial", "paytm", "cred"],
    "Edtech": ["upgrad", "byju", "unacademy", "eruditus"],
    "SaaS/B2B": ["inmobi", "freshworks", "zoho", "chargebee", "postman"],
    "D2C/Ecomm": ["mensa", "snapdeal", "nykaa", "boat"],
    "VC/PE": ["elevation capital", "3one4", "prosus", "sequoia", "tiger", "blume"],
    "DeepTech/AI": ["neysa", "nvidia", "microsoft", "isro", "ai", "ml"],
    "Mobility": ["ola", "rapido", "yulu"],
    "Government": ["government of india", "competition commission", "g20"],
}

def infer_seniority(title):
    t = title.lower()
    for tier, kws in SENIORITY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return tier
    return "Manager/IC"

def infer_industry(company, title=""):
    text = (company + " " + title).lower()
    for industry, kws in INDUSTRY_MAP.items():
        if any(kw.lower() in text for kw in kws):
            return industry
    return "Other"

def icp_score(seniority, industry):
    """
    Simple ICP score 1–5 for a pricing intelligence / data automation product.
    High value: C-Suite at Fintech/D2C/SaaS/VC
    """
    s_score = {"C-Suite": 3, "VP/Director": 2, "Manager/IC": 1}.get(seniority, 1)
    i_score = {
        "Fintech": 2, "D2C/Ecomm": 2, "SaaS/B2B": 2,
        "VC/PE": 1, "DeepTech/AI": 1, "Edtech": 1,
        "Mobility": 1, "Government": 0, "Other": 0
    }.get(industry, 0)
    raw = s_score + i_score
    return min(5, raw)  # cap at 5


# ───────────────────────────────────────────────
# PART 3: Generate mock contacts to reach 200
# ───────────────────────────────────────────────

MOCK_CONTACTS = [
    # Fintech founders / C-Suite
    {"name": "Arjun Mehta", "title": "Founder & CEO", "company": "FinStack Labs"},
    {"name": "Priya Krishnamurthy", "title": "Co-founder & COO", "company": "LendGrid"},
    {"name": "Saurabh Bhatia", "title": "Chief Product Officer", "company": "InsuranceFirst"},
    {"name": "Deepika Nair", "title": "Founder", "company": "WealthBridge"},
    {"name": "Karan Malhotra", "title": "CEO", "company": "PayFlow India"},
    {"name": "Ananya Sharma", "title": "Co-founder & CTO", "company": "CreditSense"},
    {"name": "Vikram Sinha", "title": "MD & CEO", "company": "LoanTap"},
    {"name": "Ritika Gupta", "title": "Founder & CEO", "company": "Finova Capital"},
    {"name": "Aditya Bansal", "title": "Chief Revenue Officer", "company": "RazorX"},
    {"name": "Sneha Reddy", "title": "Co-founder", "company": "NeoBank One"},
    # SaaS / B2B
    {"name": "Nikhil Anand", "title": "VP of Sales", "company": "SaaSify"},
    {"name": "Meghna Patel", "title": "Head of Growth", "company": "Chargebee"},
    {"name": "Rohit Verma", "title": "Founder & CEO", "company": "Stackr.io"},
    {"name": "Ishaan Chopra", "title": "CTO", "company": "Quickwork"},
    {"name": "Pooja Kapoor", "title": "VP Engineering", "company": "Zomentum"},
    {"name": "Alok Jain", "title": "Co-founder", "company": "Clientjoy"},
    {"name": "Kavya Rao", "title": "CEO", "company": "Sprinto"},
    {"name": "Rahul Suri", "title": "Director of Product", "company": "Rocketlane"},
    {"name": "Nandita Iyer", "title": "Chief Marketing Officer", "company": "Leadsquared"},
    {"name": "Sandeep Kumar", "title": "Founder", "company": "DemandBase India"},
    # D2C / Ecommerce
    {"name": "Tanvi Shah", "title": "Founder & CEO", "company": "Plum Goodness"},
    {"name": "Ayush Tiwari", "title": "Co-founder", "company": "Bey Bee"},
    {"name": "Shruti Bose", "title": "CEO", "company": "Snitch Fashion"},
    {"name": "Mihir Khanna", "title": "Head of D2C", "company": "Mamaearth"},
    {"name": "Prerna Singh", "title": "Founder", "company": "Aastey"},
    {"name": "Vivek Sharma", "title": "VP Ecommerce", "company": "Nykaa"},
    {"name": "Rashmi Tomar", "title": "Co-founder & CMO", "company": "Blissclub"},
    {"name": "Ankit Garg", "title": "CEO", "company": "WOW Skin Science"},
    {"name": "Divya Menon", "title": "Founder", "company": "Pilgrim India"},
    {"name": "Siddharth Roy", "title": "Head of Growth", "company": "The Moms Co"},
    # VC / Investors
    {"name": "Sunil Goyal", "title": "General Partner", "company": "YourNest Ventures"},
    {"name": "Aditi Avasthi", "title": "Partner", "company": "Blume Ventures"},
    {"name": "Ramakrishna Reddy", "title": "Managing Partner", "company": "Ideaspring Capital"},
    {"name": "Gauri Shankar", "title": "Principal", "company": "Matrix Partners India"},
    {"name": "Nitin Sharma", "title": "Founding Partner", "company": "Antler India"},
    {"name": "Roshni Mistry", "title": "Partner", "company": "Lightspeed India"},
    {"name": "Arun Natarajan", "title": "General Partner", "company": "Ventureintelligence"},
    {"name": "Shyam Menon", "title": "Investment Director", "company": "Stellaris Venture Partners"},
    {"name": "Ishita Dalmia", "title": "VP Investments", "company": "Omidyar Network India"},
    {"name": "Manish Agarwal", "title": "Partner", "company": "Nexus Venture Partners"},
    # DeepTech / AI
    {"name": "Vijay Anand", "title": "Founder & CEO", "company": "Sarvam AI"},
    {"name": "Poornima Rajan", "title": "CTO", "company": "Mad Street Den"},
    {"name": "Krishnamurthy Subramanian", "title": "Co-founder", "company": "Ola Krutrim"},
    {"name": "Aishwarya Srinivasan", "title": "Head of AI", "company": "IDFC First Bank"},
    {"name": "Saurav Jha", "title": "Founder", "company": "Detect Technologies"},
    {"name": "Lakshmi Balasubramanian", "title": "VP AI Research", "company": "Flipkart"},
    {"name": "Rahul Dey", "title": "Co-founder & CEO", "company": "Haptik"},
    {"name": "Priya Mathur", "title": "Chief AI Officer", "company": "Mphasis"},
    {"name": "Tarun Mehta", "title": "Founder & CEO", "company": "Ather Energy"},
    {"name": "Devendra Parulekar", "title": "Partner", "company": "SQream Technologies"},
    # Edtech
    {"name": "Pawan Munjal", "title": "MD", "company": "Hero Vired"},
    {"name": "Sanjay Salunkhe", "title": "CEO", "company": "Imarticus Learning"},
    {"name": "Neha Aggarwal", "title": "Co-founder & COO", "company": "Classplus"},
    {"name": "Abhimanyu Saxena", "title": "Co-founder", "company": "Scaler Academy"},
    {"name": "Ashwin Damera", "title": "CEO", "company": "Eruditus"},
    {"name": "Nikhil Barshikar", "title": "Founder", "company": "Imarticus"},
    {"name": "Beas Dev Ralhan", "title": "CEO", "company": "Next Education"},
    {"name": "Richa Kar", "title": "Co-founder", "company": "Zivame"},
    {"name": "Yamini Bhat", "title": "Co-founder & CEO", "company": "Vymo"},
    {"name": "Sonal Verma", "title": "VP Learning", "company": "BYJU's"},
    # Large Enterprise / CXOs
    {"name": "Rajan Anandan", "title": "VP India & SE Asia", "company": "Sequoia Capital"},
    {"name": "Shankar Narayanan", "title": "MD India", "company": "Carlyle Group"},
    {"name": "Aparna Ballakur", "title": "Country Head", "company": "Google for Startups India"},
    {"name": "Shalini Pillay", "title": "Office Managing Partner", "company": "KPMG India"},
    {"name": "Sangeeta Gupta", "title": "SVP & Chief Evangelist", "company": "NASSCOM"},
    {"name": "Ritesh Agarwal", "title": "Founder & CEO", "company": "OYO"},
    {"name": "Siddharth Sharma", "title": "Head of Startup Ecosystem", "company": "AWS India"},
    {"name": "Prashant Pansare", "title": "Director Enterprise Sales", "company": "Salesforce India"},
    {"name": "Sunitha Lal", "title": "COO", "company": "Kotak Ventures"},
    {"name": "Vikram Ahuja", "title": "Co-founder", "company": "Talent500"},
    # Healthtech / Climatetech
    {"name": "Prashant Tandon", "title": "Co-founder & CEO", "company": "1mg"},
    {"name": "Gaurav Gupta", "title": "Founder", "company": "Eka Care"},
    {"name": "Nandini Mansinghka", "title": "CEO", "company": "Mumbai Angels Network"},
    {"name": "Anmol Jaggi", "title": "Co-founder", "company": "BluSmart Mobility"},
    {"name": "Shreya Mishra", "title": "Founder", "company": "Phool.co"},
    {"name": "Hemant Beniwal", "title": "CTO", "company": "Pristyn Care"},
    {"name": "Vikram Vuppala", "title": "Founder & CEO", "company": "NephroPlus"},
    {"name": "Aashish Solanki", "title": "Head of Product", "company": "Curefit"},
    {"name": "Keerthi Reddy", "title": "Co-founder", "company": "Zypp Electric"},
    {"name": "Ankur Pahwa", "title": "Partner", "company": "EY India"},
    # More Founders / Misc
    {"name": "Girish Mathrubootham", "title": "Founder & Executive Chairman", "company": "Freshworks"},
    {"name": "Shekhar Kirani", "title": "Partner", "company": "Accel India"},
    {"name": "Mekin Maheshwari", "title": "Founder", "company": "Udhyam Learning Foundation"},
    {"name": "Harsh Shah", "title": "Co-founder", "company": "Fynd"},
    {"name": "Aarti Ahuja", "title": "Co-founder & CEO", "company": "Stretch Money"},
    {"name": "Abhinav Lal", "title": "CTO & Co-founder", "company": "Healthifyme"},
    {"name": "Vikas Garg", "title": "Co-founder", "company": "Beato"},
    {"name": "Sanjeev Bikhchandani", "title": "Founder", "company": "Info Edge"},
    {"name": "Anupam Mittal", "title": "Founder & CEO", "company": "Shaadi.com"},
    {"name": "Deepinder Goyal", "title": "Co-founder & CEO", "company": "Zomato"},
    {"name": "Neeraj Arora", "title": "Co-founder", "company": "My11Circle"},
    {"name": "Kalaari Capital", "title": "Partner", "company": "Kalaari Capital"},
    {"name": "Amit Lakhotia", "title": "Founder & CEO", "company": "Park+"},
    {"name": "Ruchit Garg", "title": "Founder & CEO", "company": "Harvesting"},
    {"name": "Supam Maheshwari", "title": "Founder & CEO", "company": "FirstCry"},
    {"name": "Pradeep MS", "title": "Head of Partnerships", "company": "Juspay"},
    {"name": "Mohit Bhatnagar", "title": "Managing Director", "company": "Sequoia India"},
    {"name": "Tarun Tahiliani", "title": "Founder", "company": "Ensemble"},
    {"name": "Jyoti Bansal", "title": "Founder & CEO", "company": "Harness"},
    {"name": "Karan Bajaj", "title": "Founder & CEO", "company": "WhiteHat Jr"},
    {"name": "Rishab Malik", "title": "Partner", "company": "Vertex Ventures"},
    {"name": "Neha Dhupia", "title": "Chief Brand Officer", "company": "MamaEarth"},
    {"name": "Amarpreet Kalkat", "title": "Founder & CEO", "company": "Humanic AI"},
    {"name": "Vibhore Goyal", "title": "Co-founder", "company": "Helpshift"},
    {"name": "Sanjay Mehta", "title": "Founder", "company": "100X.VC"},
    {"name": "Asha Jadeja", "title": "Partner", "company": "Motwani Jadeja Foundation"},
    {"name": "Prashanth Prakash", "title": "Partner", "company": "Accel India"},
    {"name": "Arpit Agarwal", "title": "Partner", "company": "Blume Ventures"},
    {"name": "Prayank Swaroop", "title": "Partner", "company": "Accel India"},
    {"name": "Padmaja Ruparel", "title": "Co-founder", "company": "Indian Angel Network"},
    {"name": "Shailendra Singh", "title": "Managing Director", "company": "Peak XV Partners"},
    {"name": "Ravi Adusumalli", "title": "Managing Partner", "company": "SAIF Partners"},
    {"name": "Vani Kola", "title": "Managing Director", "company": "Kalaari Capital"},
    {"name": "Nandini Vaidyanathan", "title": "Founder", "company": "CARMa Connect"},
    {"name": "Mridul Arora", "title": "Partner", "company": "Saama Capital"},
    {"name": "Sudhir Sethi", "title": "Founder & Chairman", "company": "Chiratae Ventures"},
    {"name": "Parag Dhol", "title": "Managing Director", "company": "Inventus Capital India"},
    {"name": "Arun Kumar", "title": "CTO", "company": "Infosys BPM"},
    {"name": "Rekha Menon", "title": "Chairperson", "company": "Accenture India"},
    {"name": "Harshil Mathur", "title": "CEO & Co-founder", "company": "Razorpay"},
    {"name": "Kunal Shah", "title": "Founder & CEO", "company": "CRED"},
    {"name": "Sameer Nigam", "title": "Founder & CEO", "company": "PhonePe"},
    {"name": "Sriharsha Majety", "title": "Co-founder & CEO", "company": "Swiggy"},
    {"name": "Hari TN", "title": "Chief People Officer", "company": "BigBasket"},
    {"name": "Sujeet Kumar", "title": "Co-founder", "company": "Udaan"},
    {"name": "Ranjit Satyanath", "title": "Director Engineering", "company": "Flipkart"},
    {"name": "Jayendra Patel", "title": "VP Product", "company": "Meesho"},
    {"name": "Akash Gehani", "title": "Co-founder & COO", "company": "Instamojo"},
    {"name": "Rishikesha Krishnan", "title": "Director", "company": "IIM Bangalore"},
    {"name": "Suchit Bachalli", "title": "CEO", "company": "Unilog"},
    {"name": "Pallavi Tyagi", "title": "Head of Marketing", "company": "MoEngage"},
    {"name": "Ravi Shankar", "title": "VP Sales", "company": "Salesken"},
    {"name": "Kanika Tekriwal", "title": "Founder & CEO", "company": "JetSetGo"},
    {"name": "Anand Chandrasekaran", "title": "Chief Product Officer", "company": "Airtel"},
    {"name": "Karan Mehrotra", "title": "Co-founder", "company": "Society9"},
    {"name": "Yagnesh Sanghrajka", "title": "CFO", "company": "100X.VC"},
    {"name": "Rohan Mirchandani", "title": "Co-founder & CEO", "company": "Epigamia"},
    {"name": "Sreejith Moolayil", "title": "Co-founder", "company": "True Elements"},
    {"name": "Arshad Chaudhary", "title": "VP Business Development", "company": "Bigbasket"},
    {"name": "Veena Ashiya", "title": "Founder & CEO", "company": "Monrow Shoes"},
    {"name": "Smita Deorah", "title": "Co-founder", "company": "LEAD School"},
    {"name": "Neeraj Gupta", "title": "CEO", "company": "Policybazaar UAE"},
    {"name": "Sharad Sharma", "title": "Co-founder", "company": "iSPIRT Foundation"},
    {"name": "Nakul Kumar", "title": "Co-founder & COO", "company": "Cashify"},
    {"name": "Varun Dua", "title": "Founder & CEO", "company": "Acko Insurance"},
    {"name": "Ambarish Mitra", "title": "Co-founder", "company": "Blippar"},
    {"name": "Manish Patel", "title": "Founder", "company": "Moki"},
    {"name": "Shubhranshu Singh", "title": "VP Marketing", "company": "Tata Motors"},
    {"name": "Ajay Data", "title": "Founder & CEO", "company": "Data XGen Technologies"},
    {"name": "Sonal Saldanha", "title": "Country Director", "company": "Endeavor India"},
    {"name": "Bindisha Sarang", "title": "Head of Content", "company": "Paytm Insider"},
    {"name": "Vishal Gondal", "title": "Founder & CEO", "company": "GOQii"},
    {"name": "Ankur Warikoo", "title": "Founder", "company": "Nearbuy"},
    {"name": "Chirag Jain", "title": "Co-founder & CEO", "company": "Ezetap"},
    {"name": "Aparajita Amar", "title": "Co-founder", "company": "Sirona Hygiene"},
    {"name": "Sonica Aron", "title": "Founder & MD", "company": "Marching Sheep"},
    {"name": "Rajiv Mehta", "title": "VP Strategy", "company": "Wipro Ventures"},
    {"name": "Priya Mohan", "title": "Head of Product", "company": "upGrad"},
    {"name": "Mohit Sadaani", "title": "Co-founder & CEO", "company": "The Moms Co"},
    {"name": "Piyush Jain", "title": "Co-founder", "company": "Simpl"},
    {"name": "Mansi Jain", "title": "VP Partnerships", "company": "Spinny"},
    {"name": "Tushar Vashisht", "title": "Co-founder & CEO", "company": "Healthifyme"},
    {"name": "Sanchit Vir Gogia", "title": "Chief Analyst & CEO", "company": "Greyhound Research"},
]

# Add source field to all mock contacts
for c in MOCK_CONTACTS:
    c["source"] = "mock_realistic"


# ───────────────────────────────────────────────
# PART 4: Assemble master 200-row CSV
# ───────────────────────────────────────────────

def build_master_list(scraped_speakers, mock_contacts, target=200):
    """Merge scraped + mock contacts, enrich, deduplicate, trim to target."""
    all_contacts = scraped_speakers + mock_contacts

    enriched = []
    seen_names = set()

    for c in all_contacts:
        norm_name = c["name"].lower().strip()
        if norm_name in seen_names:
            continue
        seen_names.add(norm_name)

        seniority = infer_seniority(c.get("title", ""))
        industry = infer_industry(c.get("company", ""), c.get("title", ""))
        score = icp_score(seniority, industry)

        enriched.append({
            "id": len(enriched) + 1,
            "name": c["name"],
            "title": c["title"],
            "company": c["company"],
            "seniority_tier": seniority,
            "industry_vertical": industry,
            "icp_score": score,
            "source": c.get("source", "unknown"),
            "linkedin_url": "",          # To be filled in Phase 2 (Apollo / PhantomBuster)
            "email": "",                 # To be filled in Phase 2 (Apollo)
            "company_size": "",          # To be filled in Phase 2
            "funding_stage": "",         # To be filled in Phase 2
            "persona_summary": "",       # To be filled in Phase 3 (LLM)
            "context_hook": "",          # To be filled in Phase 3 (LLM)
            "personalization_themes": "",# To be filled in Phase 3 (LLM)
            "confidence_flag": "",       # To be filled in Phase 3 (LLM)
            "assigned_to": "",           # To be filled in Phase 5 (routing)
            "outreach_status": "pending",
            "in_sequence": "FALSE",
        })

        if len(enriched) >= target:
            break

    return enriched


def save_csv(rows, filename):
    if not rows:
        print(f"[WARN] No rows to save to {filename}")
        return
    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False)
    print(f"[✓] Saved {len(df)} rows → {filename}")


# ───────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  TechSparks 2024 — AI/GTM Automation: Step 1 Scraper")
    print("=" * 55)

    # Step 1: Scrape
    print("\n▶ STEP 1: Scraping TechSparks 2024 speakers...")
    scraped = scrape_techsparks_speakers()
    save_csv(scraped, "techsparks_speakers_raw.csv")

    # Step 2: Build master list
    print("\n▶ STEP 2: Building 200-contact master list...")
    master = build_master_list(scraped, MOCK_CONTACTS, target=200)
    save_csv(master, "techsparks_contacts_200.csv")

    # Summary
    print("\n" + "=" * 55)
    print("  SUMMARY")
    print("=" * 55)
    df = pd.DataFrame(master)
    print(f"  Total contacts    : {len(df)}")
    print(f"  Real (scraped)    : {len(df[df['source'].str.contains('fallback|scraped')])}")
    print(f"  Mock              : {len(df[df['source'] == 'mock_realistic'])}")
    print(f"\n  Seniority breakdown:")
    print(df['seniority_tier'].value_counts().to_string())
    print(f"\n  Industry breakdown:")
    print(df['industry_vertical'].value_counts().to_string())
    print(f"\n  ICP Score distribution:")
    print(df['icp_score'].value_counts().sort_index(ascending=False).to_string())
    print("\n  ✅ Done. Next step: open techsparks_contacts_200.csv")
    print("     and import into Google Sheets for Phase 2 enrichment.\n")
