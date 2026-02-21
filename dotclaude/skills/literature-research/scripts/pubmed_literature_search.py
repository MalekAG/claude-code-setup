#!/usr/bin/env python3
"""
Literature search tool for PubMed and ClinicalTrials.gov.
Retrieves studies based on search criteria and outputs structured data.

Uses NCBI E-utilities (free, no API key required for low volume).
"""

import os
import sys
import json
import argparse
import time
import re
from datetime import datetime
from typing import Optional
import requests
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

# NCBI E-utilities base URLs
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# ClinicalTrials.gov API (v2)
CT_SEARCH_URL = "https://clinicaltrials.gov/api/v2/studies"


def search_pubmed(query: str, max_results: int = 1000, min_date: str = None, max_date: str = None) -> list:
    """
    Search PubMed and return list of PMIDs.

    Args:
        query: PubMed search query
        max_results: Maximum number of results to retrieve
        min_date: Minimum publication date (YYYY/MM/DD or YYYY)
        max_date: Maximum publication date (YYYY/MM/DD or YYYY)

    Returns:
        List of PMIDs
    """
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
    }

    if min_date:
        params["mindate"] = min_date
        params["datetype"] = "pdat"
    if max_date:
        params["maxdate"] = max_date
        params["datetype"] = "pdat"

    print(f"Searching PubMed: {query[:100]}...")

    try:
        response = requests.get(PUBMED_SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        pmids = data.get("esearchresult", {}).get("idlist", [])
        total_count = int(data.get("esearchresult", {}).get("count", 0))

        print(f"  Found {total_count} total results, retrieving {len(pmids)}")
        return pmids

    except Exception as e:
        print(f"  Error searching PubMed: {e}", file=sys.stderr)
        return []


def fetch_pubmed_details(pmids: list, batch_size: int = 100) -> list:
    """
    Fetch detailed information for a list of PMIDs.

    Args:
        pmids: List of PubMed IDs
        batch_size: Number of articles to fetch per request

    Returns:
        List of article dictionaries
    """
    articles = []

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        print(f"  Fetching details for articles {i+1}-{i+len(batch)} of {len(pmids)}...")

        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "rettype": "abstract"
        }

        try:
            response = requests.get(PUBMED_FETCH_URL, params=params, timeout=60)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.content)

            for article_elem in root.findall(".//PubmedArticle"):
                article = parse_pubmed_article(article_elem)
                if article:
                    articles.append(article)

            # Rate limiting - NCBI requests max 3 requests/second without API key
            time.sleep(0.4)

        except Exception as e:
            print(f"    Error fetching batch: {e}", file=sys.stderr)
            continue

    return articles


def parse_pubmed_article(article_elem) -> Optional[dict]:
    """
    Parse a PubMed article XML element into a dictionary.
    """
    try:
        medline = article_elem.find(".//MedlineCitation")
        if medline is None:
            return None

        pmid = medline.findtext(".//PMID", "")

        article = medline.find(".//Article")
        if article is None:
            return None

        # Title
        title = article.findtext(".//ArticleTitle", "")

        # Abstract
        abstract_parts = []
        for abstract_text in article.findall(".//AbstractText"):
            label = abstract_text.get("Label", "")
            text = "".join(abstract_text.itertext())
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Authors
        authors = []
        for author in article.findall(".//Author"):
            last_name = author.findtext("LastName", "")
            fore_name = author.findtext("ForeName", "")
            if last_name:
                authors.append(f"{last_name} {fore_name}".strip())

        # Journal
        journal = article.findtext(".//Journal/Title", "")
        journal_abbrev = article.findtext(".//Journal/ISOAbbreviation", "")

        # Publication date
        pub_date = article.find(".//PubDate")
        year = pub_date.findtext("Year", "") if pub_date is not None else ""
        month = pub_date.findtext("Month", "") if pub_date is not None else ""
        day = pub_date.findtext("Day", "") if pub_date is not None else ""
        pub_date_str = f"{year}-{month}-{day}".strip("-")

        # Publication types
        pub_types = [pt.text for pt in article.findall(".//PublicationType") if pt.text]

        # MeSH terms
        mesh_terms = [mh.findtext("DescriptorName", "") for mh in medline.findall(".//MeshHeading")]
        mesh_terms = [m for m in mesh_terms if m]

        # Keywords
        keywords = [kw.text for kw in medline.findall(".//Keyword") if kw.text]

        # DOI
        doi = ""
        for article_id in article_elem.findall(".//ArticleId"):
            if article_id.get("IdType") == "doi":
                doi = article_id.text or ""
                break

        # Determine study type
        study_type = classify_study_type(pub_types, title, abstract)

        return {
            "source": "PubMed",
            "pmid": pmid,
            "doi": doi,
            "title": title,
            "authors": "; ".join(authors[:10]),  # Limit to first 10 authors
            "journal": journal,
            "journal_abbrev": journal_abbrev,
            "pub_date": pub_date_str,
            "pub_year": year,
            "abstract": abstract,
            "pub_types": "; ".join(pub_types),
            "mesh_terms": "; ".join(mesh_terms),
            "keywords": "; ".join(keywords),
            "study_type": study_type,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        }

    except Exception as e:
        print(f"    Error parsing article: {e}", file=sys.stderr)
        return None


def classify_study_type(pub_types: list, title: str, abstract: str) -> str:
    """
    Classify the study type based on publication types and content.
    """
    pub_types_lower = [pt.lower() for pt in pub_types]
    title_lower = title.lower()
    abstract_lower = abstract.lower()

    # Check publication types first
    if any("randomized controlled trial" in pt for pt in pub_types_lower):
        return "RCT"
    if any("clinical trial" in pt for pt in pub_types_lower):
        return "Clinical Trial"
    if any("meta-analysis" in pt for pt in pub_types_lower):
        return "Meta-Analysis"
    if any("systematic review" in pt for pt in pub_types_lower):
        return "Systematic Review"
    if any("review" in pt for pt in pub_types_lower):
        return "Review"
    if any("observational study" in pt for pt in pub_types_lower):
        return "Observational"
    if any("cohort" in pt for pt in pub_types_lower):
        return "Cohort Study"
    if any("case-control" in pt for pt in pub_types_lower):
        return "Case-Control"

    # Check title/abstract for clues
    combined = title_lower + " " + abstract_lower

    if "randomized" in combined and ("controlled" in combined or "trial" in combined):
        return "RCT"
    if "meta-analysis" in combined:
        return "Meta-Analysis"
    if "systematic review" in combined:
        return "Systematic Review"
    if "cohort" in combined:
        return "Cohort Study"
    if "case-control" in combined or "case control" in combined:
        return "Case-Control"
    if "cross-sectional" in combined or "cross sectional" in combined:
        return "Cross-Sectional"
    if "retrospective" in combined:
        return "Retrospective Study"
    if "prospective" in combined:
        return "Prospective Study"
    if "observational" in combined:
        return "Observational"

    return "Other"


def search_clinical_trials(query: str, max_results: int = 500, min_date: str = None) -> list:
    """
    Search ClinicalTrials.gov for relevant studies.

    Args:
        query: Search query
        max_results: Maximum number of results
        min_date: Minimum start date (YYYY-MM-DD)

    Returns:
        List of trial dictionaries
    """
    trials = []
    page_size = 100
    page_token = None

    print(f"Searching ClinicalTrials.gov: {query[:100]}...")

    while len(trials) < max_results:
        params = {
            "query.term": query,
            "pageSize": min(page_size, max_results - len(trials)),
            "format": "json"
        }

        if page_token:
            params["pageToken"] = page_token

        if min_date:
            params["filter.advanced"] = f"AREA[StartDate]RANGE[{min_date},MAX]"

        try:
            response = requests.get(CT_SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            studies = data.get("studies", [])
            if not studies:
                break

            for study in studies:
                trial = parse_clinical_trial(study)
                if trial:
                    trials.append(trial)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

            print(f"  Retrieved {len(trials)} trials so far...")
            time.sleep(0.3)

        except Exception as e:
            print(f"  Error searching ClinicalTrials.gov: {e}", file=sys.stderr)
            break

    print(f"  Found {len(trials)} trials total")
    return trials


def parse_clinical_trial(study: dict) -> Optional[dict]:
    """
    Parse a ClinicalTrials.gov study into a dictionary.
    """
    try:
        protocol = study.get("protocolSection", {})

        # Identification
        id_module = protocol.get("identificationModule", {})
        nct_id = id_module.get("nctId", "")
        title = id_module.get("officialTitle", "") or id_module.get("briefTitle", "")

        # Status
        status_module = protocol.get("statusModule", {})
        overall_status = status_module.get("overallStatus", "")
        start_date = status_module.get("startDateStruct", {}).get("date", "")
        completion_date = status_module.get("completionDateStruct", {}).get("date", "")

        # Description
        desc_module = protocol.get("descriptionModule", {})
        brief_summary = desc_module.get("briefSummary", "")
        detailed_desc = desc_module.get("detailedDescription", "")

        # Design
        design_module = protocol.get("designModule", {})
        study_type = design_module.get("studyType", "")
        phases = design_module.get("phases", [])

        design_info = design_module.get("designInfo", {})
        allocation = design_info.get("allocation", "")
        intervention_model = design_info.get("interventionModel", "")
        masking_info = design_info.get("maskingInfo", {})
        masking = masking_info.get("masking", "")

        # Enrollment
        enrollment_info = design_module.get("enrollmentInfo", {})
        enrollment = enrollment_info.get("count", "")

        # Conditions
        conditions_module = protocol.get("conditionsModule", {})
        conditions = conditions_module.get("conditions", [])
        keywords = conditions_module.get("keywords", [])

        # Interventions
        arms_module = protocol.get("armsInterventionsModule", {})
        interventions = arms_module.get("interventions", [])
        intervention_names = [i.get("name", "") for i in interventions]
        intervention_types = [i.get("type", "") for i in interventions]

        # Outcomes
        outcomes_module = protocol.get("outcomesModule", {})
        primary_outcomes = outcomes_module.get("primaryOutcomes", [])
        primary_outcome_measures = [o.get("measure", "") for o in primary_outcomes]

        # Eligibility
        eligibility_module = protocol.get("eligibilityModule", {})
        eligibility_criteria = eligibility_module.get("eligibilityCriteria", "")
        sex = eligibility_module.get("sex", "")
        min_age = eligibility_module.get("minimumAge", "")
        max_age = eligibility_module.get("maximumAge", "")

        # Sponsor
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        lead_sponsor = sponsor_module.get("leadSponsor", {})
        sponsor_name = lead_sponsor.get("name", "")

        # Results (if available)
        results_section = study.get("resultsSection", {})
        has_results = bool(results_section)

        # Classify as RCT or Observational
        classified_type = "Observational"
        if study_type == "INTERVENTIONAL":
            if allocation and "RANDOM" in allocation.upper():
                classified_type = "RCT"
            else:
                classified_type = "Clinical Trial"

        return {
            "source": "ClinicalTrials.gov",
            "pmid": "",
            "doi": "",
            "nct_id": nct_id,
            "title": title,
            "authors": sponsor_name,  # Use sponsor as proxy
            "journal": "",
            "journal_abbrev": "",
            "pub_date": start_date,
            "pub_year": start_date[:4] if start_date else "",
            "abstract": brief_summary,
            "pub_types": study_type,
            "mesh_terms": "; ".join(conditions),
            "keywords": "; ".join(keywords),
            "study_type": classified_type,
            "url": f"https://clinicaltrials.gov/study/{nct_id}",
            # Additional CT.gov specific fields
            "ct_status": overall_status,
            "ct_phases": "; ".join(phases) if phases else "",
            "ct_enrollment": str(enrollment),
            "ct_allocation": allocation,
            "ct_masking": masking,
            "ct_interventions": "; ".join(intervention_names),
            "ct_primary_outcomes": "; ".join(primary_outcome_measures[:3]),
            "ct_completion_date": completion_date,
            "ct_has_results": "Yes" if has_results else "No"
        }

    except Exception as e:
        print(f"    Error parsing trial: {e}", file=sys.stderr)
        return None


def deduplicate_results(pubmed_articles: list, trials: list) -> list:
    """
    Combine and deduplicate results from PubMed and ClinicalTrials.gov.
    """
    all_results = []
    seen_titles = set()

    # Add PubMed articles first (generally more complete)
    for article in pubmed_articles:
        title_normalized = article["title"].lower().strip()
        if title_normalized not in seen_titles:
            seen_titles.add(title_normalized)
            # Add CT.gov specific fields as empty for PubMed articles
            article["nct_id"] = ""
            article["ct_status"] = ""
            article["ct_phases"] = ""
            article["ct_enrollment"] = ""
            article["ct_allocation"] = ""
            article["ct_masking"] = ""
            article["ct_interventions"] = ""
            article["ct_primary_outcomes"] = ""
            article["ct_completion_date"] = ""
            article["ct_has_results"] = ""
            all_results.append(article)

    # Add trials that aren't duplicates
    for trial in trials:
        title_normalized = trial["title"].lower().strip()
        if title_normalized not in seen_titles:
            seen_titles.add(title_normalized)
            all_results.append(trial)

    return all_results


def save_results(results: list, output_file: str):
    """
    Save results to JSON file.
    """
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved {len(results)} results to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Search PubMed and ClinicalTrials.gov for literature",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search
  python pubmed_literature_search.py --query "menopause hormone therapy"

  # With date range and custom output
  python pubmed_literature_search.py --query "menopause SSRI" --min_year 1994 --output results.json

  # High volume search
  python pubmed_literature_search.py --query "diabetes" --max_pubmed 5000 --max_trials 1000
        """
    )

    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--min_year", type=int, default=1994, help="Minimum publication year (default: 1994)")
    parser.add_argument("--max_year", type=int, default=None, help="Maximum publication year (default: current)")
    parser.add_argument("--max_pubmed", type=int, default=2000, help="Max PubMed results (default: 2000)")
    parser.add_argument("--max_trials", type=int, default=500, help="Max ClinicalTrials.gov results (default: 500)")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--pubmed_only", action="store_true", help="Only search PubMed")
    parser.add_argument("--trials_only", action="store_true", help="Only search ClinicalTrials.gov")

    args = parser.parse_args()

    # Set date range
    min_date = str(args.min_year) if args.min_year else None
    max_date = str(args.max_year) if args.max_year else None

    # Output file
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(".tmp", exist_ok=True)
        args.output = f".tmp/literature_search_{timestamp}.json"

    pubmed_articles = []
    trials = []

    # Search PubMed
    if not args.trials_only:
        pmids = search_pubmed(args.query, max_results=args.max_pubmed, min_date=min_date, max_date=max_date)
        if pmids:
            pubmed_articles = fetch_pubmed_details(pmids)

    # Search ClinicalTrials.gov
    if not args.pubmed_only:
        min_ct_date = f"{args.min_year}-01-01" if args.min_year else None
        trials = search_clinical_trials(args.query, max_results=args.max_trials, min_date=min_ct_date)

    # Combine and deduplicate
    all_results = deduplicate_results(pubmed_articles, trials)

    # Sort by year (newest first)
    all_results.sort(key=lambda x: x.get("pub_year", "0"), reverse=True)

    # Save results
    save_results(all_results, args.output)

    # Print summary
    study_type_counts = {}
    for r in all_results:
        st = r.get("study_type", "Unknown")
        study_type_counts[st] = study_type_counts.get(st, 0) + 1

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total results: {len(all_results)}")
    print(f"  - From PubMed: {len(pubmed_articles)}")
    print(f"  - From ClinicalTrials.gov: {len(trials)}")
    print(f"\nBy study type:")
    for st, count in sorted(study_type_counts.items(), key=lambda x: -x[1]):
        print(f"  - {st}: {count}")
    print(f"\nOutput file: {args.output}")

    return args.output


if __name__ == "__main__":
    output_file = main()
    # Print just the filename for easy piping
    if output_file:
        print(f"\n__OUTPUT_FILE__:{output_file}")
