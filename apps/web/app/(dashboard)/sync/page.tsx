import { PageHeader, PlannedFeature } from "@/components/ui";

export default function Page() {
  return (
    <>
      <PageHeader title="Profile Sync" />
      <PlannedFeature phase={5}>Portal-specific profile content, change previews and sync history. Where a portal cannot be updated automatically, you get the exact text and manual steps.</PlannedFeature>
    </>
  );
}
