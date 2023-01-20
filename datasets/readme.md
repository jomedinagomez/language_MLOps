
# Preparing dataset for Multi Label Classification task

The data is expected to be in jsonl format as described [here](https://jsonlines.org/)

## Dataset columns

Multi label classification expects following columns to be present in dataset


- **sentence1_key**: key describing sentence1 in the dataset
- **sentence2_key**: key describing sentence1 in the dataset
- **label_key**: key of the labels that are to be classified

The sentence1 and sentence2 are optional and you can input either both or any one of them

**Note.1:** *Dataset might contain additional columns but only the columns necessary for the task will be considered and rest will be ignored*
<br>
**Note.2:** *Avoid using "label", "labels" and "label_id" as the label_key for your dataset as it might generate conflicts with dataset columns of processed dataset*  

## Sample Data

Following is a sample data for single label classification task, this is derived from go_emotions dataset

```
{"text":"Thank you friend","labels":[15],"id":"eeqd04y","labels_str":"['15']"}
{"text":"Happy to be able to help.","labels":[17],"id":"efeu6uo","labels_str":"['17']"}
{"text":"that is what retardation looks like","labels":[27],"id":"eeb9aft","labels_str":"['27']"}
{"text":"I miss them being alive","labels":[16,25],"id":"ee8mzwa","labels_str":"['16', '25']"}
{"text":"Super, thanks","labels":[15],"id":"ef462jc","labels_str":"['15']"}
```

You can view the full dataset here [go_emotions dataset](https://huggingface.co/datasets/go_emotions/viewer/simplified/train)
