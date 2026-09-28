import dynamic from "next/dynamic";

const TheogonyGraph = dynamic(() => import("../components/TheogonyGraph"), {
  ssr: false,
});

export default function Home() {
  return (
    <main className="h-screen w-screen">
      <TheogonyGraph />
    </main>
  );
}
