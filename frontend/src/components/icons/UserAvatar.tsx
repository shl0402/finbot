// frontend/src/components/icons/UserAvatar.tsx
import { User } from "lucide-react";

export default function UserAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center flex-shrink-0">
      <User size={16} className="text-gray-300" />
    </div>
  );
}
