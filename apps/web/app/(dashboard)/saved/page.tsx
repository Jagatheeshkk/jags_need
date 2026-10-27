import { PageHeader, PlannedFeature } from "@/components/ui";

export default function Page() {
  return (
    <>
      <PageHeader title="Saved Jobs" />
      <PlannedFeature phase={2}>Jobs you save from Job Discovery, with match scores and your feedback on match quality.</PlannedFeature>
    </>
  );
}
