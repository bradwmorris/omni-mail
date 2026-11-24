# Use the inbox

[Back to the Omni Mail walkthrough](../README.md)

## Sync and process mail

1. Open [Omni Mail](http://127.0.0.1:8765) and click **Sync mail** to pull
   up to 50 inbox threads per Gmail account. Open a row in **Inbox** to read
   the conversation. New mail appears as **Unprocessed** for the selected
   model until you process it.
2. Tick a few familiar emails and click **Process selected**. Include
   examples of both **Action** and **No Action**.
3. Look in **No Action** for anything the model missed and in **Action**
   for messages you would have ignored. Once you’ve checked those decisions,
   click **Process remaining** to run the model on the rest.

**Unprocessed** shows what’s waiting for the selected model. Each model or
profile keeps its own decisions. A reply you owe or a failed payment to
check can be **Action**. A routine update or completed request is usually
**No Action**.

## Compare stock d1-2B with JEV
1. Pick three to five borderline emails. Try a payment notice that could be
   a receipt or a failed charge, a follow-up where it’s unclear who owes
   the next step, or a reminder that sounds urgent. Decide how you’d label
   each one before looking at either model’s result.
2. In **Inbox**, choose **d1-2B** with its original profile, tick those
   threads, and click **Process selected**. Jot down each label.
3. [Connect a JEV provider](models.md#use-jev) if you haven’t already. Switch to
   **JEV**, select the same threads again, and click **Process selected**.
   Choose email text you’re comfortable sending to your provider.
4. Compare where the models disagree against your own labels. Check which
   model missed a real action or flagged something you’d ignore. You can
   switch between models to revisit their saved decisions.
