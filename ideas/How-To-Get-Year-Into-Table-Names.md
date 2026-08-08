I&#39;m assuming that the answer is yes, but in template.yaml, if I have two parameters defined, such as Year and table, can I concatenate them when I define that as &quot;Year&quot;-&quot;table&quot; to manage the &quot;2026-table&quot; definitions?  Was that a clear question?

---

Yes, clear question! And yes, you can do this with the `!Sub` intrinsic function.

For example, if you have a `Year` parameter and want to build table names like `2026-Schedule`, `2026-Log`, etc.:

```yaml
Parameters:
  Year:
    Type: String
    Default: "2026"

  FBPScheduleTableName:
    Type: String
    Default: !Sub "${Year}-Schedule"  # ❌ Won't work in Parameters section
```

**Caveat:** `!Sub` does NOT work in the `Parameters` section — only in `Resources`, `Outputs`, and similar sections.

The right approach is to define just the `Year` parameter and use `!Sub` inline wherever you reference the table name:

```yaml
Parameters:
  Year:
    Type: String
    Default: "2026"

Resources:
  SomeFunction:
    Properties:
      Environment:
        Variables:
          FBPScheduleTableName: !Sub "${Year}-Schedule"
          FBPLogsTableName: !Sub "${Year}-Log"
          FBPTeamRecordsTableName: !Sub "${Year}-Record"
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Sub "${Year}-Schedule"
```

So looking at your template, you could replace these three parameters:

```yaml
  FBPScheduleTableName:
    Default: 2025-Schedule
  FBPLogsTableName:
    Default: 2025-Log
  FBPTeamRecordsTableName:
    Default: 2025-Record
```

...with a single `Year` parameter and use `!Sub "${Year}-Schedule"`, `!Sub "${Year}-Log"`, `!Sub "${Year}-Record"` everywhere those are referenced. That way changing the year for a new season is a one-parameter change.

---

Thanks.  That&#39;s just what I need.  I&#39;m going to restructure my DB table names so that I can just define the year and the table creation will occur automatically.

---

That's a clean approach. When you're ready to implement it, the main things to update in your template will be:

1. Remove `FBPScheduleTableName`, `FBPLogsTableName`, `FBPTeamRecordsTableName` (and `FBPWeeklyResults2025TableName` if you want to fold the year into that too)
2. Add a single `Year` parameter
3. Replace all `!Ref FBPScheduleTableName` etc. with `!Sub "${Year}-Schedule"` throughout the Resources section

If you also have DynamoDB table resource definitions in the template (like `AWS::DynamoDB::Table`), those will automatically get the right names too since they'd use the same `!Sub` pattern.

Let me know when you're ready to make the changes and I can help update the template.

---

Not ready yet, but soon.  Many thanks

---

Sounds good, looking forward to helping when you're ready!