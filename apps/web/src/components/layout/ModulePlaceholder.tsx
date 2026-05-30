import Link from "next/link";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ModulePlaceholder({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-6 py-24 text-center">
      <div className="brand-gradient mb-5 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-sm">
        <Sparkles className="h-7 w-7" />
      </div>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        {description ?? "该模块正在建设中，敬请期待。"}
      </p>
      <Link href="/" className="mt-6">
        <Button variant="outline">返回开始工作</Button>
      </Link>
      <p className="mt-10 text-xs text-muted">
        迭代 1 已搭建登录鉴权、主框架与首页，各业务模块将逐步接入真实能力
      </p>
    </div>
  );
}
