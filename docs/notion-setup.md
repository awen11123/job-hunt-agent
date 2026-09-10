# Notion Setup

Create one private Notion page that will hold the recruiting tracker, then share only
that page with your Notion integration. The local bootstrap script creates four private
data sources under it:

- 投递记录
- 流程日志
- 面试记录
- 复习任务

Set these local user environment variables first:

```powershell
[Environment]::SetEnvironmentVariable("NOTION_TOKEN", "<your Notion integration token>", "User")
[Environment]::SetEnvironmentVariable("NOTION_PARENT_PAGE_ID", "<your shared parent page id>", "User")
```

Then run:

```bash
rtk python scripts/notion_bootstrap.py
```

The script writes the generated data source IDs back to local user environment variables:

- `NOTION_APPLICATIONS_DB_ID`
- `NOTION_ACTIVITY_DB_ID`
- `NOTION_INTERVIEWS_DB_ID`
- `NOTION_REVIEW_TASKS_DB_ID`

The `*_DB_ID` names are kept for compatibility, but with the current Notion API they
store data source IDs. Do not paste tokens, page IDs, real job-search records, or Notion
URLs into chat logs or commit them to GitHub.

The bootstrap script also keeps the default Notion screens readable by configuring slim
views instead of deleting fields, and creates or reuses one `秋招总览` page with linked
table views for all four data sources:

- `投递记录`: `总览`, `待跟进`, `完整字段`
- `流程日志`: `总览`, `完整字段`
- `面试记录`: `总览`, `面试安排`, `完整字段`
- `复习任务`: `总览`, `复习看板`, `完整字段`

`总览` and the work views show only day-to-day columns. `完整字段` keeps the full schema
available for debugging, model analysis, and future automation.
