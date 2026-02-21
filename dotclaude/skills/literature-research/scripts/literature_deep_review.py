#!/usr/bin/env python3
"""
Deep literature review pipeline for systematic reviews.

This script:
1. Searches PubMed with refined queries for specific comparisons
2. Checks PMC for free full-text availability
3. Downloads available full texts from PMC
4. Extracts results data from ClinicalTrials.gov
5. Uses Unpaywall to find additional free versions
6. Outputs an enriched dataset ready for AI analysis

Designed for: HRT vs SSRI/SNRI/fezolinetant vs placebo in menopause
"""

import os
import sys
import json
import argparse
import time
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from xml.etree import ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

# API endpoints
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PMC_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
PMC_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CT_SEARCH_URL = "https://clinicaltrials.gov/api/v2/studies"
UNPAYWALL_URL = "https://api.unpaywall.org/v2"

# Your email for Unpaywall (required)
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "research@example.com")


class LiteratureReviewPipeline:
    def __init__(self, output_dir: str = ".tmp/literature_review"):
        self.output_dir = output_dir
        self.full_texts_dir = os.path.join(output_dir, "full_texts")
        os.makedirs(self.full_texts_dir, exist_ok=True)

        self.results = []
        self.stats = {
            "pubmed_found": 0,
            "pmc_available": 0,
            "full_texts_downloaded": 0,
            "ct_results_found": 0,
            "unpaywall_found": 0
        }

    def search_pubmed_refined(self, base_query: str, max_results: int = 2000,
                               min_year: int = 1994) -> List[str]:
        """
        Search PubMed with refined query.
        """
        params = {
            "db": "pubmed",
            "term": base_query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
            "mindate": str(min_year),
            "maxdate": str(datetime.now().year),
            "datetype": "pdat"
        }

        print(f"\n{'='*60}")
        print("STEP 1: Searching PubMed")
        print(f"{'='*60}")
        print(f"Query: {base_query[:100]}...")

        try:
            response = requests.get(PUBMED_SEARCH_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            pmids = data.get("esearchresult", {}).get("idlist", [])
            total = int(data.get("esearchresult", {}).get("count", 0))

            print(f"Found {total} total results, retrieving {len(pmids)}")
            self.stats["pubmed_found"] = len(pmids)
            return pmids

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return []

    def fetch_pubmed_details(self, pmids: List[str], batch_size: int = 100) -> List[Dict]:
        """
        Fetch detailed article info from PubMed.
        """
        print(f"\n{'='*60}")
        print("STEP 2: Fetching PubMed article details")
        print(f"{'='*60}")

        articles = []

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            print(f"  Fetching {i+1}-{i+len(batch)} of {len(pmids)}...")

            params = {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
                "rettype": "abstract"
            }

            try:
                response = requests.get(PUBMED_FETCH_URL, params=params, timeout=60)
                response.raise_for_status()
                root = ET.fromstring(response.content)

                for article_elem in root.findall(".//PubmedArticle"):
                    article = self._parse_pubmed_article(article_elem)
                    if article:
                        articles.append(article)

                time.sleep(0.35)

            except Exception as e:
                print(f"    Error: {e}", file=sys.stderr)
                continue

        print(f"  Retrieved {len(articles)} articles")
        return articles

    def _parse_pubmed_article(self, article_elem) -> Optional[Dict]:
        """Parse PubMed XML to dict."""
        try:
            medline = article_elem.find(".//MedlineCitation")
            if medline is None:
                return None

            pmid = medline.findtext(".//PMID", "")
            article = medline.find(".//Article")
            if article is None:
                return None

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
                last = author.findtext("LastName", "")
                first = author.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())

            # Journal
            journal = article.findtext(".//Journal/Title", "")

            # Date
            pub_date = article.find(".//PubDate")
            year = pub_date.findtext("Year", "") if pub_date is not None else ""

            # Publication types
            pub_types = [pt.text for pt in article.findall(".//PublicationType") if pt.text]

            # DOI
            doi = ""
            for aid in article_elem.findall(".//ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text or ""
                    break

            # PMC ID
            pmc_id = ""
            for aid in article_elem.findall(".//ArticleId"):
                if aid.get("IdType") == "pmc":
                    pmc_id = aid.text or ""
                    break

            # Study type classification
            study_type = self._classify_study_type(pub_types, title, abstract)

            return {
                "pmid": pmid,
                "pmc_id": pmc_id,
                "doi": doi,
                "title": title,
                "authors": "; ".join(authors[:10]),
                "journal": journal,
                "pub_year": year,
                "abstract": abstract,
                "pub_types": "; ".join(pub_types),
                "study_type": study_type,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                # To be filled later
                "pmc_full_text": "",
                "full_text_available": "No",
                "full_text_source": "",
                "ct_nct_id": "",
                "ct_status": "",
                "ct_enrollment": "",
                "ct_results_available": "",
                "ct_primary_outcome": "",
                "ct_outcome_results": "",
                "interventions_extracted": "",
                "comparators_extracted": "",
                "outcomes_extracted": "",
                "effect_sizes_extracted": ""
            }

        except Exception as e:
            return None

    def _classify_study_type(self, pub_types: list, title: str, abstract: str) -> str:
        """Classify study type from metadata."""
        pub_lower = [pt.lower() for pt in pub_types]
        combined = (title + " " + abstract).lower()

        if any("randomized controlled trial" in pt for pt in pub_lower):
            return "RCT"
        if any("clinical trial" in pt for pt in pub_lower):
            return "Clinical Trial"
        if any("meta-analysis" in pt for pt in pub_lower):
            return "Meta-Analysis"
        if any("systematic review" in pt for pt in pub_lower):
            return "Systematic Review"
        if "randomized" in combined and "trial" in combined:
            return "RCT"
        if "meta-analysis" in combined:
            return "Meta-Analysis"
        if "systematic review" in combined:
            return "Systematic Review"
        if "cohort" in combined:
            return "Cohort"
        if "cross-sectional" in combined:
            return "Cross-Sectional"
        if any("review" in pt for pt in pub_lower):
            return "Review"

        return "Other"

    def check_pmc_availability(self, articles: List[Dict]) -> List[Dict]:
        """
        Check which articles have free full text in PMC.
        """
        print(f"\n{'='*60}")
        print("STEP 3: Checking PMC full-text availability")
        print(f"{'='*60}")

        pmc_count = 0
        for article in articles:
            if article.get("pmc_id"):
                pmc_count += 1
                article["full_text_available"] = "Yes"
                article["full_text_source"] = "PMC"

        print(f"  {pmc_count} articles have PMC full text available")
        self.stats["pmc_available"] = pmc_count
        return articles

    def download_pmc_full_texts(self, articles: List[Dict], max_downloads: int = 500) -> List[Dict]:
        """
        Download full texts from PMC.
        """
        print(f"\n{'='*60}")
        print("STEP 4: Downloading PMC full texts")
        print(f"{'='*60}")

        pmc_articles = [a for a in articles if a.get("pmc_id")][:max_downloads]
        print(f"  Downloading {len(pmc_articles)} full texts...")

        downloaded = 0
        for i, article in enumerate(pmc_articles):
            if (i + 1) % 50 == 0:
                print(f"    Progress: {i+1}/{len(pmc_articles)}")

            pmc_id = article["pmc_id"]
            if not pmc_id.startswith("PMC"):
                pmc_id = f"PMC{pmc_id}"

            try:
                # Fetch full text XML from PMC
                params = {
                    "db": "pmc",
                    "id": pmc_id.replace("PMC", ""),
                    "rettype": "xml",
                    "retmode": "xml"
                }

                response = requests.get(PMC_FETCH_URL, params=params, timeout=30)
                if response.status_code == 200:
                    # Parse and extract text content
                    full_text = self._extract_text_from_pmc_xml(response.content)
                    if full_text:
                        article["pmc_full_text"] = full_text
                        downloaded += 1

                        # Save to file
                        filepath = os.path.join(self.full_texts_dir, f"{pmc_id}.txt")
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(full_text)

                time.sleep(0.35)

            except Exception as e:
                continue

        print(f"  Downloaded {downloaded} full texts")
        self.stats["full_texts_downloaded"] = downloaded
        return articles

    def _extract_text_from_pmc_xml(self, xml_content: bytes) -> str:
        """
        Extract readable text from PMC XML.
        """
        try:
            root = ET.fromstring(xml_content)

            text_parts = []

            # Get article title
            title = root.findtext(".//article-title", "")
            if title:
                text_parts.append(f"TITLE: {title}\n")

            # Get abstract
            abstract_elem = root.find(".//abstract")
            if abstract_elem is not None:
                abstract_text = " ".join(abstract_elem.itertext())
                text_parts.append(f"\nABSTRACT:\n{abstract_text}\n")

            # Get body sections
            body = root.find(".//body")
            if body is not None:
                for sec in body.findall(".//sec"):
                    sec_title = sec.findtext("title", "")
                    if sec_title:
                        text_parts.append(f"\n{sec_title.upper()}:\n")

                    for p in sec.findall(".//p"):
                        p_text = " ".join(p.itertext())
                        if p_text.strip():
                            text_parts.append(p_text + "\n")

            # Get tables (extract captions and data)
            for table_wrap in root.findall(".//table-wrap"):
                caption = table_wrap.findtext(".//caption/p", "") or table_wrap.findtext(".//caption/title", "")
                if caption:
                    text_parts.append(f"\n[TABLE: {caption}]\n")

            # Get figures (captions only)
            for fig in root.findall(".//fig"):
                caption = fig.findtext(".//caption/p", "") or fig.findtext(".//caption/title", "")
                if caption:
                    text_parts.append(f"\n[FIGURE: {caption}]\n")

            return " ".join(text_parts)

        except Exception as e:
            return ""

    def check_unpaywall(self, articles: List[Dict], max_checks: int = 500) -> List[Dict]:
        """
        Check Unpaywall for additional free full texts.
        """
        print(f"\n{'='*60}")
        print("STEP 5: Checking Unpaywall for free versions")
        print(f"{'='*60}")

        # Only check articles without PMC full text that have DOIs
        to_check = [a for a in articles
                    if not a.get("pmc_full_text") and a.get("doi")][:max_checks]

        print(f"  Checking {len(to_check)} articles without PMC...")

        found = 0
        for i, article in enumerate(to_check):
            if (i + 1) % 100 == 0:
                print(f"    Progress: {i+1}/{len(to_check)}")

            doi = article["doi"]
            try:
                url = f"{UNPAYWALL_URL}/{doi}?email={UNPAYWALL_EMAIL}"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("is_oa"):
                        best_loc = data.get("best_oa_location", {})
                        if best_loc:
                            article["full_text_available"] = "Yes"
                            article["full_text_source"] = best_loc.get("host_type", "Unpaywall")
                            article["full_text_url"] = best_loc.get("url_for_pdf") or best_loc.get("url")
                            found += 1

                time.sleep(0.1)  # Unpaywall rate limit

            except Exception:
                continue

        print(f"  Found {found} additional free versions")
        self.stats["unpaywall_found"] = found
        return articles

    def search_clinical_trials(self, query: str, max_results: int = 500) -> List[Dict]:
        """
        Search ClinicalTrials.gov and get results data.
        """
        print(f"\n{'='*60}")
        print("STEP 6: Searching ClinicalTrials.gov")
        print(f"{'='*60}")

        trials = []
        page_token = None

        while len(trials) < max_results:
            params = {
                "query.term": query,
                "pageSize": min(100, max_results - len(trials)),
                "format": "json",
                "fields": "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,EnrollmentCount,"
                         "StartDate,CompletionDate,Condition,Intervention,PrimaryOutcome,"
                         "SecondaryOutcome,StudyType,DesignAllocation,DesignMasking,"
                         "LeadSponsorName,ResultsFirstSubmitDate"
            }

            if page_token:
                params["pageToken"] = page_token

            try:
                response = requests.get(CT_SEARCH_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                studies = data.get("studies", [])
                if not studies:
                    break

                for study in studies:
                    trial = self._parse_trial_with_results(study)
                    if trial:
                        trials.append(trial)

                page_token = data.get("nextPageToken")
                if not page_token:
                    break

                print(f"  Retrieved {len(trials)} trials...")
                time.sleep(0.3)

            except Exception as e:
                print(f"  Error: {e}", file=sys.stderr)
                break

        print(f"  Found {len(trials)} trials total")
        return trials

    def _parse_trial_with_results(self, study: dict) -> Optional[Dict]:
        """
        Parse ClinicalTrials.gov study with focus on results.
        """
        try:
            protocol = study.get("protocolSection", {})
            results = study.get("resultsSection", {})

            # Basic info
            id_mod = protocol.get("identificationModule", {})
            nct_id = id_mod.get("nctId", "")
            title = id_mod.get("officialTitle", "") or id_mod.get("briefTitle", "")

            # Status
            status_mod = protocol.get("statusModule", {})
            status = status_mod.get("overallStatus", "")
            start_date = status_mod.get("startDateStruct", {}).get("date", "")

            # Design
            design_mod = protocol.get("designModule", {})
            study_type = design_mod.get("studyType", "")
            phases = design_mod.get("phases", [])
            enrollment = design_mod.get("enrollmentInfo", {}).get("count", "")

            design_info = design_mod.get("designInfo", {})
            allocation = design_info.get("allocation", "")
            masking = design_info.get("maskingInfo", {}).get("masking", "")

            # Conditions & Interventions
            cond_mod = protocol.get("conditionsModule", {})
            conditions = cond_mod.get("conditions", [])

            arms_mod = protocol.get("armsInterventionsModule", {})
            interventions = arms_mod.get("interventions", [])
            intervention_names = [i.get("name", "") for i in interventions]
            intervention_types = [i.get("type", "") for i in interventions]

            # Arms/Groups
            arms = arms_mod.get("armGroups", [])
            arm_labels = [a.get("label", "") for a in arms]

            # Outcomes
            outcomes_mod = protocol.get("outcomesModule", {})
            primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
            primary_measures = [o.get("measure", "") for o in primary_outcomes]

            # Results data (if available)
            has_results = bool(results)
            results_summary = ""
            outcome_results = ""

            if has_results:
                # Baseline characteristics
                baseline = results.get("baselineCharacteristicsModule", {})

                # Outcome measures
                outcome_measures = results.get("outcomeMeasuresModule", {})
                if outcome_measures:
                    measures = outcome_measures.get("outcomeMeasures", [])
                    outcome_parts = []
                    for measure in measures[:5]:  # First 5 outcomes
                        m_title = measure.get("title", "")
                        m_type = measure.get("type", "")

                        # Get group data
                        groups = measure.get("groups", [])
                        classes = measure.get("classes", [])

                        if classes:
                            for cls in classes[:2]:  # First 2 classes
                                categories = cls.get("categories", [])
                                for cat in categories[:1]:
                                    measurements = cat.get("measurements", [])
                                    values = []
                                    for m in measurements:
                                        grp = m.get("groupId", "")
                                        val = m.get("value", "")
                                        spread = m.get("spread", "")
                                        if val:
                                            values.append(f"{grp}:{val}±{spread}" if spread else f"{grp}:{val}")
                                    if values:
                                        outcome_parts.append(f"{m_title}: {', '.join(values)}")

                    outcome_results = "; ".join(outcome_parts)

            # Classify study type
            classified = "Observational"
            if study_type == "INTERVENTIONAL":
                if allocation and "RANDOM" in allocation.upper():
                    classified = "RCT"
                else:
                    classified = "Clinical Trial"

            return {
                "source": "ClinicalTrials.gov",
                "ct_nct_id": nct_id,
                "title": title,
                "ct_status": status,
                "ct_phases": "; ".join(phases) if phases else "",
                "ct_enrollment": str(enrollment),
                "ct_allocation": allocation,
                "ct_masking": masking,
                "study_type": classified,
                "conditions": "; ".join(conditions),
                "interventions": "; ".join(intervention_names),
                "intervention_types": "; ".join(intervention_types),
                "arms": "; ".join(arm_labels),
                "primary_outcomes": "; ".join(primary_measures),
                "has_results": "Yes" if has_results else "No",
                "outcome_results": outcome_results,
                "start_date": start_date,
                "url": f"https://clinicaltrials.gov/study/{nct_id}"
            }

        except Exception as e:
            return None

    def fetch_ct_results_for_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Try to match PubMed articles to ClinicalTrials.gov entries and get results.
        """
        print(f"\n{'='*60}")
        print("STEP 7: Matching articles to ClinicalTrials.gov")
        print(f"{'='*60}")

        # Search for NCT IDs in abstracts
        nct_pattern = re.compile(r'NCT\d{8}', re.IGNORECASE)

        matched = 0
        for article in articles:
            abstract = article.get("abstract", "")
            title = article.get("title", "")

            # Look for NCT ID
            matches = nct_pattern.findall(abstract + " " + title)
            if matches:
                nct_id = matches[0].upper()
                article["ct_nct_id"] = nct_id

                # Fetch trial data
                trial_data = self._fetch_single_trial(nct_id)
                if trial_data:
                    article["ct_status"] = trial_data.get("ct_status", "")
                    article["ct_enrollment"] = trial_data.get("ct_enrollment", "")
                    article["ct_results_available"] = trial_data.get("has_results", "No")
                    article["ct_primary_outcome"] = trial_data.get("primary_outcomes", "")
                    article["ct_outcome_results"] = trial_data.get("outcome_results", "")
                    matched += 1

        print(f"  Matched {matched} articles to CT.gov entries")
        self.stats["ct_results_found"] = matched
        return articles

    def _fetch_single_trial(self, nct_id: str) -> Optional[Dict]:
        """Fetch a single trial from CT.gov."""
        try:
            url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                study = response.json()
                return self._parse_trial_with_results(study)
        except:
            pass
        return None

    def extract_intervention_details(self, articles: List[Dict]) -> List[Dict]:
        """
        Use regex to extract intervention details from abstracts.
        """
        print(f"\n{'='*60}")
        print("STEP 8: Extracting intervention details")
        print(f"{'='*60}")

        # Patterns for interventions
        hrt_patterns = [
            r'estrogen', r'estradiol', r'conjugated equine estrogen', r'CEE',
            r'hormone therapy', r'hormone replacement', r'HRT', r'MHT',
            r'transdermal estrogen', r'oral estrogen', r'estrogen\s*\+\s*progest'
        ]

        ssri_snri_patterns = [
            r'paroxetine', r'venlafaxine', r'escitalopram', r'citalopram',
            r'sertraline', r'fluoxetine', r'desvenlafaxine', r'duloxetine',
            r'SSRI', r'SNRI', r'serotonin reuptake'
        ]

        other_patterns = [
            r'fezolinetant', r'elinzanetant', r'NK3', r'neurokinin',
            r'gabapentin', r'clonidine', r'placebo'
        ]

        for article in articles:
            text = (article.get("abstract", "") + " " + article.get("title", "")).lower()

            interventions = []
            comparators = []

            # Check HRT
            for pattern in hrt_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    interventions.append("HRT/Estrogen")
                    break

            # Check SSRI/SNRI
            for pattern in ssri_snri_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    match = re.search(pattern, text, re.IGNORECASE)
                    interventions.append(match.group(0).title())
                    break

            # Check other
            for pattern in other_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    match = re.search(pattern, text, re.IGNORECASE)
                    if "placebo" in match.group(0).lower():
                        comparators.append("Placebo")
                    else:
                        interventions.append(match.group(0).title())

            article["interventions_extracted"] = "; ".join(set(interventions))
            article["comparators_extracted"] = "; ".join(set(comparators))

            # Extract outcome mentions
            outcome_patterns = [
                r'hot flash(?:es)?', r'hot flush(?:es)?', r'vasomotor',
                r'night sweat', r'sleep', r'quality of life', r'QoL',
                r'frequency', r'severity', r'Kupperman', r'Greene'
            ]

            outcomes = []
            for pattern in outcome_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    outcomes.append(pattern.replace(r'(?:es)?', 's'))

            article["outcomes_extracted"] = "; ".join(set(outcomes))

        print(f"  Extracted intervention details for {len(articles)} articles")
        return articles

    def filter_relevant_studies(self, articles: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter to highly relevant studies (direct comparisons).
        """
        print(f"\n{'='*60}")
        print("STEP 9: Filtering to relevant studies")
        print(f"{'='*60}")

        highly_relevant = []
        moderately_relevant = []

        for article in articles:
            interventions = article.get("interventions_extracted", "").lower()
            comparators = article.get("comparators_extracted", "").lower()
            study_type = article.get("study_type", "")

            # Highly relevant: RCT/Clinical Trial with HRT and (SSRI/SNRI or fezolinetant) or placebo comparison
            has_hrt = "hrt" in interventions or "estrogen" in interventions
            has_ssri_snri = any(x in interventions for x in ["ssri", "snri", "paroxetine", "venlafaxine",
                                                             "escitalopram", "sertraline", "desvenlafaxine"])
            has_fezolinetant = "fezolinetant" in interventions or "elinzanetant" in interventions
            has_placebo = "placebo" in comparators

            is_trial = study_type in ["RCT", "Clinical Trial", "Meta-Analysis", "Systematic Review"]

            if is_trial:
                # Head-to-head comparison
                if (has_hrt and has_ssri_snri) or (has_hrt and has_fezolinetant):
                    highly_relevant.append(article)
                    article["relevance"] = "High - Head-to-head comparison"
                # Placebo-controlled for any of the interventions
                elif (has_hrt or has_ssri_snri or has_fezolinetant) and has_placebo:
                    highly_relevant.append(article)
                    article["relevance"] = "High - Placebo-controlled"
                # Any trial with relevant interventions
                elif has_hrt or has_ssri_snri or has_fezolinetant:
                    moderately_relevant.append(article)
                    article["relevance"] = "Moderate - Relevant intervention"
                else:
                    article["relevance"] = "Low"
            else:
                if has_hrt or has_ssri_snri or has_fezolinetant:
                    moderately_relevant.append(article)
                    article["relevance"] = "Moderate - Observational"
                else:
                    article["relevance"] = "Low"

        print(f"  Highly relevant: {len(highly_relevant)}")
        print(f"  Moderately relevant: {len(moderately_relevant)}")

        return highly_relevant, moderately_relevant

    def compile_results(self, articles: List[Dict], trials: List[Dict]) -> List[Dict]:
        """
        Compile final dataset combining all sources.
        """
        print(f"\n{'='*60}")
        print("STEP 10: Compiling final dataset")
        print(f"{'='*60}")

        # Start with articles
        all_results = articles.copy()

        # Add trials that aren't already in articles (by NCT ID)
        existing_ncts = {a.get("ct_nct_id") for a in articles if a.get("ct_nct_id")}

        for trial in trials:
            nct_id = trial.get("ct_nct_id", "")
            if nct_id and nct_id not in existing_ncts:
                # Convert trial format to article format
                all_results.append({
                    "pmid": "",
                    "pmc_id": "",
                    "doi": "",
                    "title": trial.get("title", ""),
                    "authors": "",
                    "journal": "",
                    "pub_year": trial.get("start_date", "")[:4] if trial.get("start_date") else "",
                    "abstract": "",
                    "pub_types": trial.get("study_type", ""),
                    "study_type": trial.get("study_type", ""),
                    "pubmed_url": "",
                    "pmc_full_text": "",
                    "full_text_available": "No",
                    "full_text_source": "",
                    "ct_nct_id": nct_id,
                    "ct_status": trial.get("ct_status", ""),
                    "ct_enrollment": trial.get("ct_enrollment", ""),
                    "ct_results_available": trial.get("has_results", ""),
                    "ct_primary_outcome": trial.get("primary_outcomes", ""),
                    "ct_outcome_results": trial.get("outcome_results", ""),
                    "interventions_extracted": trial.get("interventions", ""),
                    "comparators_extracted": "",
                    "outcomes_extracted": trial.get("primary_outcomes", ""),
                    "effect_sizes_extracted": "",
                    "relevance": "From ClinicalTrials.gov",
                    "source": "ClinicalTrials.gov",
                    "url": trial.get("url", "")
                })

        # Sort by relevance then year
        relevance_order = {"High - Head-to-head comparison": 0, "High - Placebo-controlled": 1,
                          "Moderate - Relevant intervention": 2, "Moderate - Observational": 3,
                          "From ClinicalTrials.gov": 4, "Low": 5, "": 6}

        all_results.sort(key=lambda x: (
            relevance_order.get(x.get("relevance", ""), 6),
            -int(x.get("pub_year") or "0")
        ))

        print(f"  Total compiled results: {len(all_results)}")
        return all_results

    def save_results(self, results: List[Dict], filename: str = None) -> str:
        """Save results to JSON."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.output_dir, f"deep_review_{timestamp}.json")

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(results)} results to {filename}")
        return filename

    def print_summary(self):
        """Print pipeline summary."""
        print(f"\n{'='*60}")
        print("PIPELINE SUMMARY")
        print(f"{'='*60}")
        for key, value in self.stats.items():
            print(f"  {key.replace('_', ' ').title()}: {value}")


def main():
    parser = argparse.ArgumentParser(description="Deep literature review pipeline")

    parser.add_argument("--query", default=None, help="Custom PubMed query")
    parser.add_argument("--min_year", type=int, default=1994, help="Minimum year")
    parser.add_argument("--max_pubmed", type=int, default=2000, help="Max PubMed results")
    parser.add_argument("--max_trials", type=int, default=500, help="Max CT.gov results")
    parser.add_argument("--max_full_texts", type=int, default=500, help="Max full texts to download")
    parser.add_argument("--output_dir", default=".tmp/literature_review", help="Output directory")
    parser.add_argument("--skip_full_text", action="store_true", help="Skip full text download")
    parser.add_argument("--skip_unpaywall", action="store_true", help="Skip Unpaywall check")

    args = parser.parse_args()

    # Default query for HRT vs SSRI/SNRI/fezolinetant in menopause
    if not args.query:
        args.query = """
        (menopause OR postmenopausal OR climacteric OR perimenopause)
        AND (vasomotor symptoms OR hot flashes OR hot flushes OR night sweats)
        AND (
            (hormone therapy OR HRT OR estrogen OR estradiol OR "conjugated equine estrogen")
            OR (SSRI OR SNRI OR paroxetine OR venlafaxine OR escitalopram OR desvenlafaxine OR sertraline)
            OR (fezolinetant OR elinzanetant OR NK3 antagonist)
        )
        AND (randomized controlled trial[pt] OR clinical trial[pt] OR meta-analysis[pt]
             OR systematic review[pt] OR comparative study OR placebo)
        """.replace("\n", " ")

    pipeline = LiteratureReviewPipeline(output_dir=args.output_dir)

    # Step 1: Search PubMed
    pmids = pipeline.search_pubmed_refined(args.query, max_results=args.max_pubmed, min_year=args.min_year)

    # Step 2: Fetch article details
    articles = pipeline.fetch_pubmed_details(pmids)

    # Step 3: Check PMC availability
    articles = pipeline.check_pmc_availability(articles)

    # Step 4: Download PMC full texts
    if not args.skip_full_text:
        articles = pipeline.download_pmc_full_texts(articles, max_downloads=args.max_full_texts)

    # Step 5: Check Unpaywall
    if not args.skip_unpaywall:
        articles = pipeline.check_unpaywall(articles)

    # Step 6: Search ClinicalTrials.gov
    ct_query = "(menopause OR postmenopausal) AND (hot flashes OR vasomotor) AND (hormone OR estrogen OR SSRI OR SNRI OR paroxetine OR venlafaxine OR fezolinetant)"
    trials = pipeline.search_clinical_trials(ct_query, max_results=args.max_trials)

    # Step 7: Match articles to CT.gov
    articles = pipeline.fetch_ct_results_for_articles(articles)

    # Step 8: Extract intervention details
    articles = pipeline.extract_intervention_details(articles)

    # Step 9: Filter relevant studies
    highly_relevant, moderately_relevant = pipeline.filter_relevant_studies(articles)

    # Step 10: Compile results
    all_results = pipeline.compile_results(articles, trials)

    # Save results
    output_file = pipeline.save_results(all_results)

    # Save highly relevant subset
    if highly_relevant:
        hr_file = os.path.join(args.output_dir, "highly_relevant_studies.json")
        with open(hr_file, "w") as f:
            json.dump(highly_relevant, f, indent=2)
        print(f"Saved {len(highly_relevant)} highly relevant studies to {hr_file}")

    pipeline.print_summary()

    print(f"\n__OUTPUT_FILE__:{output_file}")
    return output_file


if __name__ == "__main__":
    main()
