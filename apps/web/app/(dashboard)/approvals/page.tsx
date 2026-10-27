import { PageHeader, PlannedFeature } from "@/components/ui";

export default function Page() {
  return (
    <>
      <PageHeader title="Approval Queue" />
      <PlannedFeature phase={4}>Items needing your decision: legal declarations, salary commitments, sensitive attestations and unknown screening answers are never answered automatically.</PlannedFeature>
    </>
  );
}
