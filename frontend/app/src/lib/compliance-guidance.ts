/**
 * Bilingual deficiency guidance for the documents used by the validation workflow.
 *
 * Design rules:
 * - Keyed by the identifiers the API and presets actually use, with display-name aliases.
 * - A clause citation is included ONLY where the existing APH catalog already has one. Where no
 *   mapping exists, `clause` is null and the UI says so. No citation is invented here.
 * - English and Hindi live together so a handbook change updates both at once.
 * - Hindi is an unofficial reading aid; the English text and the APH prevail.
 *
 * This module intentionally has no imports so it can be unit-tested directly with Node's
 * type-stripping test runner.
 */

export type GuidanceLanguage = "en" | "hi";

export interface LocalizedText {
  en: string;
  hi: string;
}

export interface DocumentGuidance {
  /** Canonical identifier used by the API and presets. */
  id: string;
  label: LocalizedText;
  /** Alternate spellings, display names and catalog keys that resolve to this entry. */
  aliases: string[];
  /** Existing catalog citation, or null when no verified mapping exists. */
  clause: string | null;
  chapter: LocalizedText | null;
  title: LocalizedText | null;
  requirement: LocalizedText;
  impact: LocalizedText;
  mitigation: LocalizedText;
  ownerRole: LocalizedText;
  evidenceRequired: LocalizedText;
  isStatutoryZeroTolerance: boolean;
}

export const GUIDANCE_VERSION = "2026-10-30.1";

export const GUIDANCE_SOURCE_NOTE: LocalizedText = {
  en: "Clause text is carried from this project's APH catalog and is NOT yet verified against the official handbook. Treat it as a pointer for human review, not as regulation.",
  hi: "धारा-पाठ इस परियोजना की APH सूची से लिया गया है और आधिकारिक हैंडबुक से अभी सत्यापित नहीं है। इसे मानवीय समीक्षा के संकेत के रूप में देखें, विनियम के रूप में नहीं।",
};

export const DOCUMENT_GUIDANCE: DocumentGuidance[] = [
  {
    id: "aicte_approval",
    label: { en: "AICTE Approval Letter", hi: "एआईसीटीई अनुमोदन पत्र" },
    aliases: ["AICTE Approval Letter", "aicte approval", "approval letter", "LoA", "LoE"],
    clause: null,
    chapter: null,
    title: null,
    requirement: {
      en: "The current Letter of Approval or Extension covering the programmes and intake applied for, valid for the academic year of the application.",
      hi: "आवेदन में शामिल कार्यक्रमों और प्रवेश संख्या को कवर करने वाला वर्तमान अनुमोदन या विस्तार पत्र, जो आवेदन के शैक्षणिक वर्ष के लिए वैध हो।",
    },
    impact: {
      en: "Without a valid approval letter the application has no baseline to extend; scrutiny cannot proceed on the applied programme.",
      hi: "वैध अनुमोदन पत्र के बिना आवेदन के विस्तार का कोई आधार नहीं रहता; आवेदित कार्यक्रम पर जाँच आगे नहीं बढ़ सकती।",
    },
    mitigation: {
      en: "Attach the latest LoA/LoE with its validity dates, plus the receipt for the current year's extension application if the letter is pending.",
      hi: "नवीनतम LoA/LoE उसकी वैधता तिथियों सहित संलग्न करें; यदि पत्र लंबित है तो चालू वर्ष के विस्तार आवेदन की रसीद भी लगाएँ।",
    },
    ownerRole: { en: "Registrar / Principal", hi: "कुलसचिव / प्राचार्य" },
    evidenceRequired: {
      en: "A scanned LoA/LoE whose institution name and programme list match the application, with a readable validity date.",
      hi: "स्कैन किया गया LoA/LoE जिसमें संस्थान का नाम और कार्यक्रम सूची आवेदन से मेल खाती हो तथा वैधता तिथि पढ़ने योग्य हो।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "mandatory_disclosure",
    label: { en: "Mandatory Disclosure (Affidavits 1 & 2)", hi: "अनिवार्य प्रकटीकरण (शपथ पत्र 1 और 2)" },
    aliases: [
      "Mandatory Disclosure",
      "Affidavit 1 & Affidavit 2 (AICTE Portal Format)",
      "affidavits",
      "mandatory disclosure",
    ],
    clause: "Clause 2.1",
    chapter: { en: "Chapter II: Annual Self-Disclosure", hi: "अध्याय II: वार्षिक स्व-प्रकटीकरण" },
    title: { en: "Mandatory statutory self-disclosure affidavits", hi: "अनिवार्य वैधानिक स्व-प्रकटीकरण शपथ पत्र" },
    requirement: {
      en: "Duly notarised Affidavits 1 and 2 confirming accurate disclosure of the faculty roster, fees, anti-ragging measures and infrastructure.",
      hi: "संकाय सूची, शुल्क, रैगिंग-विरोधी उपायों और अवसंरचना के सही प्रकटीकरण की पुष्टि करते हुए विधिवत नोटरीकृत शपथ पत्र 1 और 2।",
    },
    impact: {
      en: "An incomplete application; it can be rejected at the online scrutiniser gate before any committee review.",
      hi: "अपूर्ण आवेदन; समिति समीक्षा से पहले ऑनलाइन जाँच चरण में ही अस्वीकार किया जा सकता है।",
    },
    mitigation: {
      en: "Re-upload the signed and notarised affidavits in the portal format, with the notary seal legible on every page.",
      hi: "हस्ताक्षरित और नोटरीकृत शपथ पत्र पोर्टल प्रारूप में पुनः अपलोड करें, हर पृष्ठ पर नोटरी मुहर स्पष्ट हो।",
    },
    ownerRole: { en: "Registrar / Principal", hi: "कुलसचिव / प्राचार्य" },
    evidenceRequired: {
      en: "Both affidavits, notarised, with the institution name and the current academic year stated on the first page.",
      hi: "दोनों शपथ पत्र नोटरीकृत, पहले पृष्ठ पर संस्थान का नाम और चालू शैक्षणिक वर्ष अंकित।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "land_use_certificate",
    label: { en: "Land Use / NA Conversion Certificate", hi: "भूमि उपयोग / एनए रूपांतरण प्रमाण पत्र" },
    aliases: [
      "Land Use Certificate",
      "Land Ownership Deed / 30-Year Registered Lease",
      "land use certificate",
      "na conversion",
    ],
    clause: "Clause 1.7",
    chapter: {
      en: "Chapter I: Establishment of New Technical Institutions",
      hi: "अध्याय I: नई तकनीकी संस्थाओं की स्थापना",
    },
    title: {
      en: "Contiguous land title and Non-Agricultural conversion",
      hi: "सतत भूमि स्वामित्व और गैर-कृषि रूपांतरण",
    },
    requirement: {
      en: "Clear, unencumbered ownership or a registered lease of at least 30 years, together with the Non-Agricultural (educational) conversion order for the campus land.",
      hi: "परिसर भूमि पर स्वच्छ, भारमुक्त स्वामित्व या कम से कम 30 वर्ष का पंजीकृत पट्टा, तथा गैर-कृषि (शैक्षणिक) रूपांतरण आदेश।",
    },
    impact: {
      en: "A title or land-use defect can disqualify the establishment or continuation application and any campus expansion.",
      hi: "स्वामित्व या भूमि-उपयोग में त्रुटि स्थापना या निरंतरता आवेदन तथा परिसर विस्तार को अयोग्य कर सकती है।",
    },
    mitigation: {
      en: "Attach the registered sub-registrar entry and mutation extract, plus the NA conversion order; if conversion is pending, attach the competent authority's receipt.",
      hi: "पंजीकृत उप-पंजीयक प्रविष्टि और परिवर्तन उतारा तथा एनए रूपांतरण आदेश संलग्न करें; रूपांतरण लंबित हो तो सक्षम प्राधिकारी की रसीद लगाएँ।",
    },
    ownerRole: { en: "Trust / Legal Cell", hi: "न्यास / विधि प्रकोष्ठ" },
    evidenceRequired: {
      en: "Registered deed or lease, the NA order, and a site plan showing the contiguous parcel and its area.",
      hi: "पंजीकृत विलेख या पट्टा, एनए आदेश, और सतत भूखंड तथा उसका क्षेत्रफल दर्शाने वाला स्थल-नक्शा।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "fire_safety_certificate",
    label: { en: "Fire Safety Certificate / NOC", hi: "अग्नि सुरक्षा प्रमाण पत्र / एनओसी" },
    aliases: ["Fire Safety Certificate", "fire safety", "fire noc", "fire_safety_certificate"],
    clause: "Clause 2.4",
    chapter: { en: "Chapter II: Extension of Approval", hi: "अध्याय II: अनुमोदन का विस्तार" },
    title: { en: "Fire and life safety clearance", hi: "अग्नि एवं जीवन सुरक्षा स्वीकृति" },
    requirement: {
      en: "A valid Fire Safety NOC from the competent State Fire Authority covering all instructional and administrative blocks.",
      hi: "सभी शैक्षणिक और प्रशासनिक भवनों को कवर करने वाला सक्षम राज्य अग्निशमन प्राधिकरण का वैध अग्नि सुरक्षा एनओसी।",
    },
    impact: {
      en: "A zero-tolerance deficiency: extension of approval can be withheld and the case summoned before the Standing Hearing Committee.",
      hi: "शून्य-सहनशीलता की कमी: अनुमोदन का विस्तार रोका जा सकता है और मामला स्थायी सुनवाई समिति के समक्ष भेजा जा सकता है।",
    },
    mitigation: {
      en: "File the AICTE Format 3 undertaking on Rs. 100 non-judicial stamp paper with the District Fire Officer's renewal application receipt.",
      hi: "जिला अग्निशमन अधिकारी के नवीनीकरण आवेदन की रसीद के साथ रु. 100 के गैर-न्यायिक स्टाम्प पेपर पर एआईसीटीई फॉर्मेट 3 का वचन-पत्र दाखिल करें।",
    },
    ownerRole: { en: "Estate & Fire Safety Officer", hi: "संपत्ति एवं अग्नि सुरक्षा अधिकारी" },
    evidenceRequired: {
      en: "The NOC itself with its validity end date, or the renewal application receipt plus the undertaking.",
      hi: "वैधता अंत तिथि सहित एनओसी, या नवीनीकरण आवेदन की रसीद और वचन-पत्र।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "building_occupancy_certificate",
    label: { en: "Building Occupancy Certificate", hi: "भवन अधिभोग प्रमाण पत्र" },
    aliases: ["Occupancy Certificate", "building occupancy", "occupancy certificate"],
    clause: "Clause 2.5",
    chapter: { en: "Chapter II: Land & Building Norms", hi: "अध्याय II: भूमि एवं भवन मानदंड" },
    title: { en: "Building occupancy and completion certificate", hi: "भवन अधिभोग एवं पूर्णता प्रमाण पत्र" },
    requirement: {
      en: "Final or provisional Occupancy Certificate from the Municipal Corporation or competent town planning authority.",
      hi: "नगर निगम या सक्षम नगर नियोजन प्राधिकारी से अंतिम या अस्थायी अधिभोग प्रमाण पत्र।",
    },
    impact: {
      en: "New programmes or campus expansion can be rejected, and the approved seat matrix may be reduced.",
      hi: "नए कार्यक्रम या परिसर विस्तार अस्वीकृत हो सकते हैं, तथा स्वीकृत सीट मैट्रिक्स घटाया जा सकता है।",
    },
    mitigation: {
      en: "Submit the architect-certified building plan with the local body application registration number while the OC is issued.",
      hi: "ओसी जारी होने तक स्थानीय निकाय आवेदन पंजीकरण संख्या सहित वास्तुकार-प्रमाणित भवन नक्शा जमा करें।",
    },
    ownerRole: { en: "Estate & Fire Safety Officer", hi: "संपत्ति एवं अग्नि सुरक्षा अधिकारी" },
    evidenceRequired: {
      en: "The OC with the sanctioned plan number and the built-up area it covers.",
      hi: "स्वीकृत नक्शा संख्या और कवर किए गए निर्मित क्षेत्र सहित ओसी।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "land_ownership_affidavit",
    label: { en: "Land Ownership Affidavit", hi: "भूमि स्वामित्व शपथ पत्र" },
    aliases: ["Land Ownership Affidavit", "land affidavit"],
    clause: null,
    chapter: null,
    title: null,
    requirement: {
      en: "A sworn affidavit identifying the owner of record and confirming lawful possession of the campus land.",
      hi: "भूमि के अभिलेखीय स्वामी की पहचान और परिसर भूमि पर वैध कब्जे की पुष्टि करता शपथ पत्र।",
    },
    impact: {
      en: "Without it the title chain is unverified and the land-use evidence cannot be tied to the applicant.",
      hi: "इसके बिना स्वामित्व श्रृंखला असत्यापित रहती है और भूमि-उपयोग प्रमाण आवेदक से नहीं जुड़ पाता।",
    },
    mitigation: {
      en: "Execute the affidavit on stamp paper, naming the applicant trust/society exactly as on the deed, and attach the deed reference.",
      hi: "स्टाम्प पेपर पर शपथ पत्र बनाएँ, उसमें आवेदक न्यास/समिति का नाम विलेख के अनुसार लिखें, और विलेख का संदर्भ संलग्न करें।",
    },
    ownerRole: { en: "Trust / Legal Cell", hi: "न्यास / विधि प्रकोष्ठ" },
    evidenceRequired: {
      en: "Notarised affidavit plus the deed/lease it refers to.",
      hi: "नोटरीकृत शपथ पत्र तथा उससे संदर्भित विलेख/पट्टा।",
    },
    isStatutoryZeroTolerance: false,
  },
  {
    id: "trust_deed",
    label: { en: "Trust / Society Registration Deed", hi: "न्यास / समिति पंजीकरण विलेख" },
    aliases: ["Trust Deed", "Society Registration", "trust deed"],
    clause: null,
    chapter: null,
    title: null,
    requirement: {
      en: "The registered trust deed or society registration document establishing the applicant as a legal entity permitted to run a technical institution.",
      hi: "आवेदक को तकनीकी संस्थान चलाने की अनुमति वाली कानूनी संस्था सिद्ध करने वाला पंजीकृत न्यास विलेख या समिति पंजीकरण दस्तावेज।",
    },
    impact: {
      en: "Without a registered parent body the application has no lawful applicant.",
      hi: "पंजीकृत मूल निकाय के बिना आवेदन का कोई विधिक आवेदक नहीं होता।",
    },
    mitigation: {
      en: "Attach the registration certificate and the clause of the deed that permits education as an object of the trust/society.",
      hi: "पंजीकरण प्रमाण पत्र और विलेख की वह धारा संलग्न करें जो शिक्षा को न्यास/समिति का उद्देश्य बताती है।",
    },
    ownerRole: { en: "Trust / Legal Cell", hi: "न्यास / विधि प्रकोष्ठ" },
    evidenceRequired: {
      en: "Registration certificate with the registration number and the operative objects clause.",
      hi: "पंजीकरण संख्या सहित पंजीकरण प्रमाण पत्र और प्रचालन-उद्देश्य धारा।",
    },
    isStatutoryZeroTolerance: false,
  },
  {
    id: "master_plan_architect_certificate",
    label: { en: "Master Plan (Architect Certificate)", hi: "मास्टर प्लान (वास्तुकार प्रमाणन)" },
    aliases: ["Master Plan Architect Certificate", "master plan", "architect certificate"],
    clause: null,
    chapter: null,
    title: null,
    requirement: {
      en: "A master plan certified by a registered architect showing the built-up area, land use and the constructed blocks against the sanctioned plan.",
      hi: "पंजीकृत वास्तुकार द्वारा प्रमाणित मास्टर प्लान, जो स्वीकृत नक्शे के सापेक्ष निर्मित क्षेत्र, भूमि उपयोग और भवनों को दर्शाए।",
    },
    impact: {
      en: "Without a certified plan, built-up area and land-use claims cannot be reconciled with the OC or the site.",
      hi: "प्रमाणित नक्शे के बिना निर्मित क्षेत्र और भूमि-उपयोग के दावे ओसी या स्थल से नहीं मिलाए जा सकते।",
    },
    mitigation: {
      en: "Obtain the architect's certified plan with registration number, signature and date, matching the sanctioned plan number.",
      hi: "स्वीकृत नक्शा संख्या से मेल खाता, पंजीकरण संख्या, हस्ताक्षर और तिथि सहित वास्तुकार-प्रमाणित नक्शा प्राप्त करें।",
    },
    ownerRole: { en: "Estate & Fire Safety Officer", hi: "संपत्ति एवं अग्नि सुरक्षा अधिकारी" },
    evidenceRequired: {
      en: "Stamped and signed plan with the architect's council registration number.",
      hi: "वास्तुकार परिषद पंजीकरण संख्या सहित मुद्रांकित और हस्ताक्षरित नक्शा।",
    },
    isStatutoryZeroTolerance: false,
  },
  {
    id: "fd_corpus_fund_receipt",
    label: { en: "Fixed Deposit (Corpus Fund) Receipt", hi: "सावधि जमा (कोष निधि) रसीद" },
    aliases: ["Fixed Deposit (Corpus Fund) Receipt", "corpus fund", "FDR"],
    clause: "Clause 1.9",
    chapter: { en: "Chapter I: Financial Solvency", hi: "अध्याय I: वित्तीय शोधनक्षमता" },
    title: { en: "Joint corpus security deposit", hi: "संयुक्त कोष सुरक्षा जमा" },
    requirement: {
      en: "An FDR in the joint name of the sponsoring trust/society and the Regional Officer, AICTE, for the prescribed lock-in period.",
      hi: "निर्धारित लॉक-इन अवधि के लिए प्रायोजक न्यास/समिति और एआईसीटीई क्षेत्रीय अधिकारी के संयुक्त नाम का एफडीआर।",
    },
    impact: {
      en: "The Letter of Approval or Extension can be withheld until the corpus is evidenced.",
      hi: "कोष सिद्ध होने तक अनुमोदन या विस्तार पत्र रोका जा सकता है।",
    },
    mitigation: {
      en: "Submit the banker's solvency certificate with the lien-creation letter to the AICTE Regional Office.",
      hi: "एआईसीटीई क्षेत्रीय कार्यालय को ग्रहणाधिकार-सृजन पत्र के साथ बैंकर का शोधनक्षमता प्रमाण पत्र जमा करें।",
    },
    ownerRole: { en: "Finance Officer", hi: "वित्त अधिकारी" },
    evidenceRequired: {
      en: "FDR advice showing joint names, amount, lock-in end date and the lien in favour of AICTE.",
      hi: "संयुक्त नाम, राशि, लॉक-इन अंत तिथि और एआईसीटीई के पक्ष में ग्रहणाधिकार दर्शाने वाली एफडीआर सलाह।",
    },
    isStatutoryZeroTolerance: true,
  },
  {
    id: "nba_accreditation",
    label: { en: "NBA Accreditation Certificate", hi: "एनबीए मान्यता प्रमाण पत्र" },
    aliases: ["NBA Accreditation Certificate", "nba", "accreditation"],
    clause: "Clause 4.2",
    chapter: {
      en: "Chapter IV: Intake Expansion & New Courses",
      hi: "अध्याय IV: प्रवेश विस्तार और नए पाठ्यक्रम",
    },
    title: { en: "Programmatic accreditation norms", hi: "कार्यक्रम-स्तरीय मान्यता मानदंड" },
    requirement: {
      en: "Valid NBA accreditation for at least 50% of eligible courses, for existing institutions seeking intake expansion.",
      hi: "प्रवेश विस्तार चाहने वाली मौजूदा संस्थाओं के लिए योग्य पाठ्यक्रमों में से कम से कम 50% के लिए वैध एनबीए मान्यता।",
    },
    impact: {
      en: "Additional divisions or specialisations can be denied, reverting the institution to base intake.",
      hi: "अतिरिक्त शाखाएँ या विशेषज्ञता अस्वीकृत हो सकती हैं, और संस्था आधार प्रवेश संख्या पर लौट सकती है।",
    },
    mitigation: {
      en: "Attach the NBA certificate with validity, or the peer-visit scheduling acknowledgement for the pending programme.",
      hi: "वैधता सहित एनबीए प्रमाण पत्र, या लंबित कार्यक्रम के लिए सहकर्मी-भ्रमण निर्धारण की पावती संलग्न करें।",
    },
    ownerRole: { en: "Academic Dean", hi: "शैक्षणिक डीन" },
    evidenceRequired: {
      en: "NBA certificate naming the programme and validity window.",
      hi: "कार्यक्रम का नाम और वैधता अवधि दर्शाने वाला एनबीए प्रमाण पत्र।",
    },
    isStatutoryZeroTolerance: false,
  },
  {
    id: "state_pollution_noc",
    label: { en: "State Pollution Control Board NOC", hi: "राज्य प्रदूषण नियंत्रण बोर्ड एनओसी" },
    aliases: ["State Pollution Control Board NOC", "pollution noc", "spcb"],
    clause: "Clause 1.8",
    chapter: { en: "Chapter I & II: Environmental clearances", hi: "अध्याय I और II: पर्यावरणीय स्वीकृतियाँ" },
    title: { en: "Consent to operate / water and air NOC", hi: "संचालन की सहमति / जल और वायु एनओसी" },
    requirement: {
      en: "Consent to Operate, or the sewage and effluent treatment certificate, from the State Pollution Control Board.",
      hi: "राज्य प्रदूषण नियंत्रण बोर्ड से संचालन की सहमति, या सीवेज और अपशिष्ट जल उपचार प्रमाण पत्र।",
    },
    impact: {
      en: "A deficiency notice with a 15-day rectification window before Regional Committee review.",
      hi: "क्षेत्रीय समिति समीक्षा से पहले 15 दिन की सुधार अवधि वाला कमी-सूचना।",
    },
    mitigation: {
      en: "File the renewal application with the verification fee challan and attach the acknowledgement.",
      hi: "सत्यापन शुल्क चालान के साथ नवीनीकरण आवेदन दाखिल करें और पावती संलग्न करें।",
    },
    ownerRole: { en: "Estate & Fire Safety Officer", hi: "संपत्ति एवं अग्नि सुरक्षा अधिकारी" },
    evidenceRequired: {
      en: "Consent order with validity, or the renewal acknowledgement with challan.",
      hi: "वैधता सहित सहमति आदेश, या चालान सहित नवीनीकरण पावती।",
    },
    isStatutoryZeroTolerance: false,
  },
  {
    id: "building_stability_certificate",
    label: { en: "Building Structural Stability Certificate", hi: "भवन संरचनात्मक स्थिरता प्रमाण पत्र" },
    aliases: ["Building Structural Stability Certificate", "structural stability", "structural certificate"],
    clause: "Clause 2.6",
    chapter: { en: "Chapter II: Infrastructure verification", hi: "अध्याय II: अवसंरचना सत्यापन" },
    title: { en: "Structural soundness certification", hi: "संरचनात्मक सुदृढ़ता प्रमाणन" },
    requirement: {
      en: "A certificate from a government-registered structural engineer confirming earthquake and structural resistance of the buildings.",
      hi: "सरकार-पंजीकृत संरचना अभियंता का प्रमाण पत्र, जो भवनों की भूकंपीय और संरचनात्मक सामर्थ्य की पुष्टि करे।",
    },
    impact: {
      en: "A severe deficiency: intake increase can be halted and an Expert Visit Committee inspection mandated.",
      hi: "गंभीर कमी: प्रवेश वृद्धि रोकी जा सकती है और विशेषज्ञ भ्रमण समिति का निरीक्षण अनिवार्य हो सकता है।",
    },
    mitigation: {
      en: "Submit the empanelled engineer's inspection affidavit stating the inspection is complete and the sealed report is pending.",
      hi: "सूचीबद्ध अभियंता का निरीक्षण शपथ पत्र जमा करें, जिसमें निरीक्षण पूर्ण और मुद्रांकित रिपोर्ट लंबित बताया गया हो।",
    },
    ownerRole: { en: "Estate & Fire Safety Officer", hi: "संपत्ति एवं अग्नि सुरक्षा अधिकारी" },
    evidenceRequired: {
      en: "Signed structural certificate with the engineer's registration number and the blocks covered.",
      hi: "अभियंता की पंजीकरण संख्या और कवर किए गए भवनों सहित हस्ताक्षरित संरचनात्मक प्रमाण पत्र।",
    },
    isStatutoryZeroTolerance: true,
  },
];

/** Lowercase and strip everything but letters and digits, so IDs and labels compare equal. */
export function normalizeDocumentKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

const INDEX: Map<string, DocumentGuidance> = (() => {
  const index = new Map<string, DocumentGuidance>();
  for (const entry of DOCUMENT_GUIDANCE) {
    index.set(normalizeDocumentKey(entry.id), entry);
    index.set(normalizeDocumentKey(entry.label.en), entry);
    for (const alias of entry.aliases) {
      index.set(normalizeDocumentKey(alias), entry);
    }
  }
  return index;
})();

export function lookupDocumentGuidance(documentId: string): DocumentGuidance | undefined {
  if (!documentId) return undefined;
  return INDEX.get(normalizeDocumentKey(documentId));
}

export function pickLocalized(text: LocalizedText, language: GuidanceLanguage): string {
  return language === "hi" ? text.hi : text.en;
}

/** UI strings for the remediation panel. Kept beside the guidance so both languages move together. */
export const PLAN_UI = {
  title: { en: "Remediation plan", hi: "सुधार योजना" },
  subtitle: {
    en: "Every deficiency becomes a task with an owner, a deadline and the evidence that closes it. Derived from this result only.",
    hi: "प्रत्येक कमी एक कार्य बनती है — जिम्मेदार अधिकारी, समय-सीमा और उसे पूरा करने वाला प्रमाण। यह केवल इस परिणाम से बना है।",
  },
  language: { en: "Guidance language", hi: "मार्गदर्शन भाषा" },
  storedLocally: {
    en: "Progress is saved in this browser only. It is not sent to a server and is not visible to anyone else. Export the CSV to share it.",
    hi: "प्रगति केवल इस ब्राउज़र में सहेजी जाती है। यह सर्वर पर नहीं भेजी जाती और किसी और को दिखाई नहीं देती। साझा करने के लिए CSV निर्यात करें।",
  },
  syncedToWorkspace: {
    en: "Saved to this institution's workspace. Other authorised officers see the same progress.",
    hi: "इस संस्थान के कार्यक्षेत्र में सहेजा गया। अन्य अधिकृत अधिकारी भी यही प्रगति देखते हैं।",
  },
  syncing: { en: "Saving progress…", hi: "प्रगति सहेजी जा रही है…" },
  syncUnavailable: {
    en: "Not saved to the server. Progress stays in this browser.",
    hi: "सर्वर पर सहेजा नहीं गया। प्रगति इस ब्राउज़र में रहती है।",
  },
  scheduleTitle: { en: "Recommended internal deadlines", hi: "अनुशंसित आंतरिक समय-सीमाएँ" },
  scheduleNote: {
    en: "These are planning recommendations for your own team. They are not AICTE deadlines and carry no official date.",
    hi: "ये आपकी टीम के लिए योजना संबंधी सुझाव हैं। ये एआईसीटीई की समय-सीमाएँ नहीं हैं और कोई आधिकारिक तिथि नहीं दर्शाती हैं।",
  },
  scheduleSharedNote: {
    en: "This plan is shared with your institution, so changing the schedule changes it for everyone. Only an institution administrator can do that, and every change is recorded.",
    hi: "यह योजना आपके संस्थान के साथ साझा है, इसलिए समय-सीमा बदलने पर वह सभी के लिए बदल जाती है। यह केवल संस्थान प्रशासक कर सकता है, और प्रत्येक परिवर्तन दर्ज होता है।",
  },
  scheduleAdminOnly: {
    en: "Only an institution administrator can change the shared schedule. Your other changes are unaffected.",
    hi: "साझा समय-सीमा केवल संस्थान प्रशासक बदल सकता है। आपके अन्य परिवर्तन प्रभावित नहीं हुए।",
  },
  scheduleHistory: {
    en: "Last schedule change",
    hi: "पिछला समय-सीमा परिवर्तन",
  },
  scheduleApplyShared: { en: "Update shared schedule", hi: "साझा समय-सीमा अपडेट करें" },
  scheduleApply: { en: "Recalculate dates", hi: "तिथियाँ पुनर्गणना करें" },
  p1Days: { en: "P1 (days)", hi: "P1 (दिन)" },
  p2Days: { en: "P2 (days)", hi: "P2 (दिन)" },
  expiryBuffer: { en: "Expiry buffer (days)", hi: "समाप्ति बफ़र (दिन)" },
  progress: { en: "Progress", hi: "प्रगति" },
  overdue: { en: "Overdue", hi: "अतिदेय" },
  due: { en: "Due", hi: "नियत तिथि" },
  owner: { en: "Owner", hi: "जिम्मेदार" },
  evidence: { en: "Evidence that closes it", hi: "इसे पूरा करने वाला प्रमाण" },
  why: { en: "Why this matters", hi: "यह क्यों महत्वपूर्ण है" },
  requirement: { en: "Requirement", hi: "आवश्यकता" },
  fix: { en: "Corrective action", hi: "सुधारात्मक कार्रवाई" },
  clause: { en: "Clause", hi: "धारा" },
  noClause: {
    en: "No clause mapped for this document — verify against the current handbook before relying on it.",
    hi: "इस दस्तावेज़ के लिए कोई धारा मैप नहीं है — भरोसा करने से पहले वर्तमान हैंडबुक से सत्यापित करें।",
  },
  exportCsv: { en: "Export plan (CSV)", hi: "योजना निर्यात करें (CSV)" },
  reset: { en: "Reset progress", hi: "प्रगति रीसेट करें" },
  details: { en: "Details", hi: "विवरण" },
  note: { en: "Note (optional)", hi: "टिप्पणी (वैकल्पिक)" },
  statusLabel: { en: "Status", hi: "स्थिति" },
  open: { en: "Open", hi: "खुला" },
  in_progress: { en: "In progress", hi: "प्रगति पर" },
  blocked: { en: "Blocked", hi: "अवरुद्ध" },
  done: { en: "Done", hi: "पूर्ण" },
  priorities: {
    P1: { en: "P1 · statutory", hi: "P1 · वैधानिक" },
    P2: { en: "P2 · required", hi: "P2 · आवश्यक" },
    P3: { en: "P3 · expiring", hi: "P3 · समाप्त होने वाला" },
  },
  unknownDocument: {
    en: "Document not in the guidance catalog",
    hi: "दस्तावेज़ मार्गदर्शन सूची में नहीं है",
  },
  unofficial: {
    en: "Hindi is an unofficial reading aid. The English text and the official handbook prevail.",
    hi: "हिन्दी अनौपचारिक सहायता है। अंग्रेज़ी पाठ और आधिकारिक हैंडबुक मान्य हैं।",
  },
} as const;
