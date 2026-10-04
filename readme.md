# FutureFlow

## The problem


## Our solution
Our app 

## How it works
The app is divided into tabs which let you organize your task management.
Everything you need focus on calender tab and tasks creations. While you add new task you can specity important parameters which affect to task prioritize and required focus span to complete the task. 
How you use this inputs depends from you. It is possible to fill gaps by hand but also using AI LLM model which based on description and your history assign right values of critical parameters such as needed focus and required time to finish task. 

Next, the list of tasks is analized by dedicated algorythm and distributed in time in your schedule. Algorythm is based on statistical REMA curve and in future will be updated using user polling. 
It takes into account user defined tags representing constant activities during the week time like sleeping or eating dinner. You can define your own tags that will allow you to specify the time ranges in which your tasks should be distributed.

## How to run

From PowerShell in the project folder:

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```

or simply:

```powershell
.\run_app.ps1
```

This project expects Python 3.14 with Tkinter support.
