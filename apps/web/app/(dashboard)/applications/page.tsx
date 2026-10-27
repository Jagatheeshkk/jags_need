import { PageHeader, PlannedFeature } from "@/components/ui";

export default function Page() {
  return (
    <>
      <PageHeader title="Application Tracker" />
      <PlannedFeature phase={3}>Every application with its status history, follow-up dates and duplicate prevention. Nothing is shown here until an application really exists.</PlannedFeature>
    </>
  );
}
