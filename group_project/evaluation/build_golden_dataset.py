"""One-shot generator for group_project/evaluation/golden_dataset.json."""
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path.cwd()
assert (ROOT / 'data/source_manifest.json').exists(), 'run from the repo root'

C = []


def case(cid, category, language, mode, question, expected_answer, expected_context,
         sources, refusal=False, notes=""):
    C.append({
        "id": cid, "category": category, "language": language, "mode": mode,
        "question": question,
        "expected_answer": expected_answer,
        "expected_context": expected_context,
        "expected_source_ids": sources,
        "expected_refusal": refusal,
        "notes": notes,
    })


# ------------------------------------------------------------------ Admissions
case("A01", "admissions", "en", "admissions",
     "What is the listed tuition fee per academic year for the Bachelor of Nursing programme?",
     "For academic year 2026-2027 the listed tuition for the Bachelor of Nursing is 349,650,000 VND per academic year over a standard duration of 4 years. The listed figure excludes the 35% Vingroup tuition subsidy.",
     "Bachelor of Nursing 4 349,650,000 174,825,000 9,780,000",
     ["admissions-tuition"])

case("A02", "admissions", "vi", "admissions",
     "Học phí niêm yết một năm của chương trình Bác sĩ Y khoa là bao nhiêu?",
     "Học phí niêm yết của chương trình Medical Doctor là 815,850,000 VND mỗi năm học, thời gian chuẩn 6 năm. Mức này chưa trừ khoản trợ cấp học phí 35% từ Vingroup.",
     "Medical Doctor 6 815,850,000 407,925,000 27,195,000",
     ["admissions-tuition"])

case("A03", "admissions", "en", "admissions",
     "What tuition subsidy does Vingroup provide and who receives it?",
     "Vingroup, the founder of VinUniversity, provides a 35% tuition subsidy. It is granted automatically to all admitted students, Vietnamese and international, and remains valid for the entire duration of study; the commitment runs from 2025 to 2030.",
     "The 35% tuition subsidy is automatically granted to all admitted students (both Vietnamese and international) and remains valid throughout the entire study period.",
     ["admissions-tuition", "admissions-scholarships"])

case("A04", "admissions", "vi", "admissions",
     "Học bổng President's Excellence Scholarship bao gồm những gì?",
     "President's Excellence Scholarship là học bổng toàn phần (full-ride), chi trả 100% học phí và chi phí sinh hoạt.",
     "President's Excellence Scholarship: Full-ride scholarship (Covers 100% of tuition and living expenses).",
     ["admissions-scholarships"])

case("A05", "admissions", "en", "admissions",
     "Which merit-based scholarship covers 80% or 90% of tuition?",
     "The Dean's Distinction Scholarship covers 80% or 90% of tuition fees.",
     "Dean's Distinction Scholarship: Covers 80% or 90% of tuition.",
     ["admissions-scholarships"])

case("A06", "admissions", "vi", "admissions",
     "Sinh viên cần GPA tối thiểu bao nhiêu để giữ học bổng toàn phần hoặc 100%?",
     "Để duy trì học bổng Full hoặc 100%, sinh viên phải giữ GPA tích lũy từ 3.2 trở lên trong năm học được xét, đồng thời không vi phạm kỷ luật mức Tier 3 hoặc Tier 4 và hoàn thành tự đánh giá E.X.C.E.L với cố vấn.",
     "Maintain a cumulative GPA of 3.2 or higher in the academic year under evaluation",
     ["entry-scholarship-maintenance-v2-1", "admissions-tuition-faq"])

case("A07", "admissions", "en", "admissions",
     "What GPA is required to renew a merit scholarship in the 50% to 90% range?",
     "Scholarships at 50%, 60%, 70%, 80% and 90% are renewed when the student maintains a cumulative GPA of 2.5 or higher for the academic year under evaluation, keeps good disciplinary standing, and completes the E.X.C.E.L self-evaluation with an advisor.",
     "Maintaining a cumulative GPA of 2.5 or higher in the academic year under evaluation",
     ["entry-scholarship-maintenance-v2-1", "admissions-tuition-faq"])

case("A08", "admissions", "en", "admissions",
     "Is the registration fee refundable after I confirm my admission?",
     "No. The registration fee is not refundable in any case, but it is deductible from the tuition fee or other payments of the first official semester, except when the variance between total payables and deductions is smaller than the fee itself.",
     "This fee is NOT refundable in all cases but deductible from the tuition fees or other payments of the official semester of the first academic year",
     ["financial-regulations-admissions"])

case("A09", "admissions", "vi", "admissions",
     "Học phí ở VinUni được đóng mấy lần trong một năm học?",
     "Học phí được đóng hai lần mỗi năm, vào đầu mỗi học kỳ chính là học kỳ Thu (Fall) và học kỳ Xuân (Spring).",
     "tuition fee payment will be made twice a year at the beginning of each main semester (Fall Semester and Spring Semester)",
     ["admissions-tuition-financial-support", "admissions-tuition-faq"])

case("A10", "admissions", "en", "admissions",
     "What is the WIT scholarship at VinUniversity?",
     "The WIT (Women in Tech) Scholarship provides an additional 5% tuition support for female applicants pursuing technology or science-related fields. It is a Special Encouragement Scholarship and is stackable with other awards.",
     "WIT (Woman in Tech) Scholarship: Provides an additional 5% tuition support for female applicants pursuing studies in technology or science-related fields.",
     ["admissions-scholarships"])

# ---------------------------------------------------------------- Student life
case("S01", "student_life", "en", "student_life",
     "What are the quiet hours in VinUni residences from Sunday to Thursday?",
     "Quiet hours run from 10:00 PM to 7:00 AM Sunday through Thursday. On Friday and Saturday they run from 12:00 AM to 7:00 AM, and adjustments may apply during holidays or exam weeks.",
     "Quiet Hours Sunday - Thursday 10:00 PM - 7:00 AM",
     ["residential-life-guideline-v5"])

case("S02", "student_life", "vi", "student_life",
     "Giờ giới nghiêm trong khu nội trú của VinUni là mấy giờ?",
     "Giờ giới nghiêm trên campus áp dụng tất cả các ngày, sau 23:00 (11:00 PM) sinh viên phải ở trong khuôn viên trường. Về muộn có thể không được vào campus.",
     "Curfew (On-campus) All days After 11:00 PM Students should remain on campus after this time.",
     ["residential-life-guideline-v5"])

case("S03", "student_life", "en", "student_life",
     "How many guests may one resident host at the same time?",
     "Each resident may have no more than three guests visiting at the same time. Guests must always be accompanied by the host and must not be given the apartment key.",
     "Each resident shall have no more than three guests visiting at the same time.",
     ["residential-life-guideline-v5"])

case("S04", "student_life", "vi", "student_life",
     "Muốn đăng ký khách ở lại qua đêm thì phải nộp đơn trước bao lâu?",
     "Sinh viên điền form Guest Visit trực tuyến trước 05 ngày làm việc đối với khách ở qua đêm, và trước 03 ngày làm việc đối với khách đến thăm trong ngày.",
     "students fill in the Guest Visit online form 03 working days in advance for visit within the day and 05 working days in advance for overnight guests.",
     ["residential-life-guideline-v5"])

case("S05", "student_life", "en", "student_life",
     "What is the minimum number of credits I must register for in one semester?",
     "The minimum number of credits required to register for one semester is 12 credits.",
     "The minimum number of credits required to register for one semester is 12 credits",
     ["academic-regulations-undergraduate-v8-1"])

case("S06", "student_life", "en", "student_life",
     "What are the criteria to be placed on the Dean's List?",
     "A student is placed on the Dean's List at the end of a regular semester with a minimum SGPA of 3.60 calculated on at least 12 letter-graded credits, no failed course among those registered, and no recorded confirmed act of major misconduct. The achievement is recorded on the transcript.",
     "Minimum SGPA 3.60 (Very Good), calculated at least 12 letter-graded credits per regular semester, have not failed any course registered",
     ["academic-regulations-undergraduate-v8-1"])

case("S07", "student_life", "vi", "student_life",
     "Khi nào một sinh viên bị đưa vào diện academic probation?",
     "Sinh viên bị academic warning hai lần liên tiếp sẽ chuyển sang diện academic probation. Khi đó sinh viên phải được cố vấn học tập phê duyệt mới được đăng ký môn, và ở diện này cho đến khi GPA tích lũy đạt 1.40/4.0 với năm hai, 1.60/4.0 với năm ba, hoặc 1.80/4.0 với năm tư trở đi.",
     "A student who is placed on academic warning two consecutive times is subject to academic probation.",
     ["academic-regulations-undergraduate-v8-1"])

case("S08", "student_life", "en", "student_life",
     "What disciplinary actions correspond to Tier 3 and Tier 4 misconduct?",
     "Tier 3 is Temporary Suspension and Tier 4 is Dismissal or Expulsion. Tier 3 and Tier 4 cases are assessed by the Student Awarding and Disciplinary Committee, which proposes the action to the Provost for final approval.",
     "Tier 1 Tier 2 Tier 3 Tier 4 Expression of Disapproval Warning Temporary Suspension Dismissal/ Expulsion",
     ["student-code-of-conduct-v5"])

case("S09", "student_life", "en", "student_life",
     "What is the minimum duration of a full-time credit-bearing internship in the Fall semester?",
     "For full-time internships the minimum duration is 7 weeks in the Fall and Spring semesters, and 6 weeks in the summer semester. Part-time internships require a minimum of 240 hours per semester.",
     "For full-time internships: Minimum duration of each 7 weeks for Fall and Spring semesters and 6 weeks for summer semester.",
     ["internship-management-v2"])

case("S10", "student_life", "vi", "student_life",
     "Sinh viên cần GPA bao nhiêu để được đăng ký kỳ thực tập tính tín chỉ?",
     "Sinh viên cần GPA tổng từ 2.0 trở lên, cùng các điều kiện tiên quyết của bộ môn phụ trách, đã hoàn thành các môn Foundation và đăng ký trong 3 tuần đầu học kỳ.",
     "Have 2.0 overall GPA, and all pre-requisites from supervising academic department.",
     ["internship-management-v2"])

# ------------------------------------------- Exact-keyword / multi-source
case("K01", "keyword_multisource", "en", "auto",
     "Compare the GPA needed to keep a full scholarship with the GPA needed for the Dean's List.",
     "They are different thresholds from two different policies. A Full or 100% merit scholarship is renewed with a cumulative GPA of 3.2 or higher for the academic year. The Dean's List requires a semester GPA of at least 3.60 on at least 12 letter-graded credits with no failed course.",
     "Maintain a cumulative GPA of 3.2 or higher in the academic year under evaluation | Minimum SGPA 3.60 (Very Good), calculated at least 12 letter-graded credits per regular semester",
     ["entry-scholarship-maintenance-v2-1", "academic-regulations-undergraduate-v8-1"],
     notes="Needs evidence from two documents; a single-chunk answer is incomplete.")

case("K02", "keyword_multisource", "vi", "auto",
     "Sau khi trừ trợ cấp 35%, sinh viên ngành Điều dưỡng còn phải đóng khoảng bao nhiêu một năm?",
     "Học phí niêm yết ngành Điều dưỡng là 349,650,000 VND mỗi năm, và tất cả sinh viên trúng tuyển được hưởng Quỹ Phát triển Giáo dục 35%. Sau khi trừ, phần còn lại khoảng 227 triệu VND mỗi năm.",
     "Nursing: 349,650,000 VND (approximately 15,000 USD) per year | the remaining tuition fee is about 227 million VND per year for the Nursing program",
     ["admissions-tuition-faq", "admissions-tuition"],
     notes="Requires combining the listed fee with the 35% subsidy figure.")

case("K03", "keyword_multisource", "en", "auto",
     "Which VinUni policy carries the reference number GDL-SAM-008?",
     "GDL-SAM-008 is the reference number of the Residential Life Guideline, version V5.0, effective 20 June 2025.",
     "GDL-SAM-008_Residential-Life-Guideline",
     ["residential-life-guideline-v5"],
     notes="Exact-keyword lookup; dense embeddings tend to miss a bare document code.")

case("K04", "keyword_multisource", "en", "auto",
     "What does E.X.C.E.L refer to in the scholarship renewal criteria?",
     "E.X.C.E.L is the self-evaluation that scholarship holders must complete and then discuss with their advisor. Completing it is one of the three renewal conditions alongside the GPA threshold and good disciplinary standing.",
     "Complete the E.X.C.E.L self-evaluation and meet with the Advisor to discuss the self-evaluation.",
     ["entry-scholarship-maintenance-v2-1"],
     notes="Exact-keyword lookup on an acronym written with periods.")

case("K05", "keyword_multisource", "vi", "auto",
     "Điều kiện duy trì học bổng yêu cầu sinh viên không được vi phạm kỷ luật ở mức nào, và mức đó tương ứng với hình thức xử lý gì?",
     "Sinh viên không được vi phạm kỷ luật mức Tier 3 (major misconduct) hoặc Tier 4 (extremely serious misconduct) theo Student Code of Conduct. Tier 3 tương ứng với đình chỉ có thời hạn và Tier 4 tương ứng với buộc thôi học.",
     "The student must not commit major misconduct (Tier 3) or extremely serious misconduct (Tier4) as per Student Code of Conduct | Tier 3 Tier 4 Temporary Suspension Dismissal/ Expulsion",
     ["entry-scholarship-maintenance-v2-1", "student-code-of-conduct-v5"],
     notes="Two documents: the scholarship guideline names the tier, the conduct policy defines it.")

# ------------------------------------------- Out of scope / insufficient
case("O01", "out_of_scope", "en", "auto",
     "What is the weather in Hanoi tomorrow?",
     "Refusal. Weather is outside the scope of the VinUni policy and admissions corpus, so the assistant should decline and point to an appropriate source instead of guessing.",
     "No supporting evidence exists in the Data Snapshot.",
     [], refusal=True)

case("O02", "out_of_scope", "vi", "auto",
     "Học phí của Đại học Quốc gia Hà Nội năm 2026 là bao nhiêu?",
     "Từ chối. Data Snapshot chỉ chứa nguồn công khai của VinUniversity, không có thông tin học phí của trường khác, nên trợ lý phải từ chối thay vì suy đoán.",
     "No supporting evidence exists in the Data Snapshot.",
     [], refusal=True)

case("O03", "out_of_scope", "en", "auto",
     "Can you look up my current GPA and my student ID number?",
     "Refusal. The assistant has no access to individual student records and must not ask for or handle personal identifiers; it should decline and direct the student to the Office of the Registrar.",
     "No supporting evidence exists in the Data Snapshot.",
     [], refusal=True)

case("O04", "out_of_scope", "vi", "auto",
     "Cho tôi số điện thoại cá nhân của Hiệu trưởng VinUni.",
     "Từ chối. Đây là thông tin cá nhân không có trong nguồn công khai của Data Snapshot, trợ lý phải từ chối cung cấp.",
     "No supporting evidence exists in the Data Snapshot.",
     [], refusal=True)

case("O05", "out_of_scope", "en", "auto",
     "How much will VinUni tuition be in the 2035-2036 academic year?",
     "Refusal. The snapshot only documents published tuition up to academic year 2026-2027, so a 2035-2036 figure cannot be verified and the assistant should decline rather than extrapolate.",
     "No supporting evidence exists in the Data Snapshot.",
     [], refusal=True)


# --------------------------------------------------------------------- checks
cats = Counter(c["category"] for c in C)
langs = Counter(c["language"] for c in C)
assert len(C) == 30, len(C)
assert cats["admissions"] == 10 and cats["student_life"] == 10, cats
assert cats["keyword_multisource"] == 5 and cats["out_of_scope"] == 5, cats
assert langs["vi"] >= 5 and langs["en"] >= 5, langs
assert len({c["id"] for c in C}) == 30
for c in C:
    for k in ("question", "expected_answer", "expected_context"):
        assert str(c[k]).strip(), (c["id"], k)
    assert c["expected_refusal"] == (c["expected_source_ids"] == []), c["id"]

manifest = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
valid = {r["source_id"] for r in manifest}
unknown = {s for c in C for s in c["expected_source_ids"]} - valid
assert not unknown, f"unknown source ids: {unknown}"

out = ROOT / "group_project/evaluation/golden_dataset.json"
out.write_text(json.dumps(C, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {len(C)} cases -> {out.relative_to(ROOT)}")
print("categories:", dict(cats))
print("languages :", dict(langs))
print("refusals  :", sum(c["expected_refusal"] for c in C))
