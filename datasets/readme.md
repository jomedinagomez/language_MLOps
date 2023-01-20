
# Preparing dataset for Single Label Classification task

The data is expected to be in jsonl format as described [here](https://jsonlines.org/)

## Dataset columns

Single label classification expects following columns to be present in dataset


- **sentence1_key**: key describing sentence1 in the dataset
- **sentence2_key**: key describing sentence1 in the dataset
- **label_key**: key of the labels that are to be classified

The sentence1 and sentence2 are optional and you can input either both or any one of them

**Note.1:** *Dataset might contain additional columns but only the columns necessary for the task will be considered and rest will be ignored*
<br>
**Note.2:** *Avoid using "label", "labels" and "label_id" as the label_key for your dataset as it might generate conflicts with dataset columns of processed dataset*  

## Sample Data

Following is a sample data for single label classification task, this is derived from glue/COLA dataset

```
{"sentence":"The moral destruction of the president was certainly not helpful.","label":1,"idx":995}
{"sentence":"Mary wants to wear nice blue German dress.","label":1,"idx":996}
{"sentence":"Tomatoes were introduced in Europe after 1492.","label":1,"idx":997}
{"sentence":"We rich have impeccable taste.","label":1,"idx":998}
{"sentence":"Rich we have impeccable taste.","label":0,"idx":999}
```

You can view the full dataset here [glue/cola dataset](https://huggingface.co/datasets/glue/viewer/cola/train)
