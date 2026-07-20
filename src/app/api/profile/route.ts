import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";

export const dynamic = "force-dynamic";
import { authOptions } from "@/lib/auth-options";
import connectDB from "@/lib/mongodb";
import User from "@/models/User";

export async function GET() {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    await connectDB();
    const user = await User.findById((session.user as any).id).select("-password").lean();

    return NextResponse.json({ user });
  } catch (error) {
    return NextResponse.json({ error: "Failed to load profile" }, { status: 500 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { name, location, farmDetails, language } = body;

    await connectDB();
    const user = await User.findByIdAndUpdate(
      (session.user as any).id,
      {
        ...(name && { name }),
        ...(location && { location }),
        ...(farmDetails && { farmDetails }),
        ...(language && { language }),
      },
      { new: true }
    ).select("-password");

    return NextResponse.json({ user, message: "Profile updated successfully" });
  } catch (error) {
    return NextResponse.json({ error: "Failed to update profile" }, { status: 500 });
  }
}
