#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
from datetime import datetime, timedelta

def create_commit_with_date(date_str, day_number):
    filename = "daily_log.txt"
    with open(filename, 'w') as f:
        f.write("="*60 + "\n")
        f.write("GIT PRACTICE SESSION - DAILY COMMIT\n")
        f.write("="*60 + "\n\n")
        f.write(f"📅 Date: {date_str}\n")
        f.write(f"📌 Day #{day_number}\n\n")
        f.write("📝 Purpose:\n")
        f.write("This is a practice commit for learning Git and GitHub.\n")
        f.write("It helps me understand:\n")
        f.write("  • Git commit history and timestamps\n")
        f.write("  • How to backdate commits\n")
        f.write("  • Git workflow automation\n")
        f.write("  • Python scripting for Git operations\n\n")
        f.write("⚠️ NOTE: This is for educational purposes only!\n")
        f.write("These commits are part of a Git practice exercise.\n")
        f.write("="*60 + "\n")

    subprocess.run(["git", "add", filename], check=True)
    
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date_str
    env["GIT_COMMITTER_DATE"] = date_str
    
    commit_msg = f"Practice: Daily Git commit - Day {day_number} ({date_str})"
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        env=env,
        check=True
    )

def main():
    print("\n" + "="*60)
    print("🔄 GIT PRACTICE SCRIPT - DAILY COMMITS")
    print("="*60)
    print("\n📚 This script creates practice commits for learning Git.")
    print("⏰ Creating one commit per day from January 1 to June 26, 2026\n")
    
    current_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 6, 26)
    day_counter = 1
    
    if not os.path.exists(".git"):
        print("📦 Initializing Git repository...")
        subprocess.run(["git", "init"], check=True)
        print("✅ Git repository initialized!\n")
    
    print("🚀 Starting to create practice commits...\n")
    
   
    while current_date <= end_date:
        
        date_str = current_date.strftime("%a, %d %b %Y 12:00:00 +0330")
        print(f"  ⏳ Creating practice commit #{day_counter}: {current_date.strftime('%Y-%m-%d')}")
        create_commit_with_date(date_str, day_counter)
        current_date += timedelta(days=1)
        day_counter += 1
    
    total_days = (end_date - datetime(2026,1,1)).days + 1
    print(f"\n✅ {total_days} practice commits created successfully!")
    print("\n" + "="*60)
    print("🎓 PRACTICE COMPLETE!")
    print("="*60)
    print("\n📖 What you practiced:")
    print("  • Creating multiple commits with custom dates")
    print("  • Using Python to automate Git operations")
    print("  • Understanding Git commit history")
    print("\n💡 Next steps:")
    print("  • Check your commit history: git log --oneline")
    print("  • Push to GitHub: git push origin main")
    print("  • View your contribution graph on GitHub")
    print("\n⚠️ Remember: This is for educational purposes only!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
