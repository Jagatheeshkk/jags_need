import { PageHeader, PlannedFeature } from "@/components/ui";

export default function Page() {
  return (
    <>
      <PageHeader title="Resume Library" />
      <PlannedFeature phase={3}>Resume upload and parsing, master and role-specific versions with file hashes, cover letters, screening-answer drafts, and DOCX/PDF export generated locally with open-source libraries.</PlannedFeature>
    </>
  );
}
