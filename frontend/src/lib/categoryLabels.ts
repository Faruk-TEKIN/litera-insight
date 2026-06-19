const CATEGORY_LABELS: Record<string, string> = {
  "cs.AI": "Artificial Intelligence",
  "cs.AR": "Hardware Architecture",
  "cs.CC": "Computational Complexity",
  "cs.CE": "Computational Engineering",
  "cs.CG": "Computational Geometry",
  "cs.CL": "Computation and Language",
  "cs.CR": "Cryptography and Security",
  "cs.CV": "Computer Vision",
  "cs.CY": "Computers and Society",
  "cs.DB": "Databases",
  "cs.DC": "Distributed Computing",
  "cs.DL": "Digital Libraries",
  "cs.DM": "Discrete Mathematics",
  "cs.DS": "Data Structures and Algorithms",
  "cs.ET": "Emerging Technologies",
  "cs.FL": "Formal Languages",
  "cs.GL": "General Literature",
  "cs.GR": "Graphics",
  "cs.GT": "Computer Science and Game Theory",
  "cs.HC": "Human-Computer Interaction",
  "cs.IR": "Information Retrieval",
  "cs.IT": "Information Theory",
  "cs.LG": "Machine Learning",
  "cs.LO": "Logic in Computer Science",
  "cs.MA": "Multiagent Systems",
  "cs.MM": "Multimedia",
  "cs.MS": "Mathematical Software",
  "cs.NA": "Numerical Analysis",
  "cs.NE": "Neural and Evolutionary Computing",
  "cs.NI": "Networking and Internet Architecture",
  "cs.OH": "Other Computer Science",
  "cs.OS": "Operating Systems",
  "cs.PF": "Performance",
  "cs.PL": "Programming Languages",
  "cs.RO": "Robotics",
  "cs.SC": "Symbolic Computation",
  "cs.SD": "Sound",
  "cs.SE": "Software Engineering",
  "cs.SI": "Social and Information Networks",
  "cs.SY": "Systems and Control",
  "econ.EM": "Econometrics",
  "econ.GN": "General Economics",
  "econ.TH": "Theoretical Economics",
  "eess.AS": "Audio and Speech Processing",
  "eess.IV": "Image and Video Processing",
  "eess.SP": "Signal Processing",
  "eess.SY": "Systems and Control",
  "math.AP": "Analysis of PDEs",
  "math.CO": "Combinatorics",
  "math.IT": "Information Theory",
  "math.NA": "Numerical Analysis",
  "math.OC": "Optimization and Control",
  "math.PR": "Probability",
  "math.ST": "Statistics Theory",
  "q-bio.NC": "Neurons and Cognition",
  "q-fin.ST": "Statistical Finance",
  "stat.AP": "Applications",
  "stat.CO": "Computation",
  "stat.ME": "Methodology",
  "stat.ML": "Machine Learning",
  "stat.TH": "Statistics Theory",
};

export function categoryLabel(category: string | null | undefined): string {
  const value = (category || "").trim();
  if (!value) return "Unknown category";
  return CATEGORY_LABELS[value] || humanizeCategory(value);
}

function humanizeCategory(value: string): string {
  const suffix = value.includes(".") ? value.split(".").slice(1).join(" ") : value;
  return suffix
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
