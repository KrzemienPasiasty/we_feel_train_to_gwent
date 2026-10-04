# FutureFlow

## The problem
We live in an era of toxic productivity and the glorification of overwork. We compete with friends over who has less free time. This traps us in a bubble, leaving no room for reflection, when the truth is that working constantly is far from the most effective way to live. We force ourselves to work even when it yields no results. We leave no time for meaningful rest, healthy meals, or physical activity, which leads to burnout, chronic stress, and strained relationships due to constant emotional tension.
According to research by the Pew Research Center, 49% of workers worry they will not be able to keep up with the tasks assigned to them.

## Our solution
Although one could attempt to solve this problem by themselves, it would require heaps of work and time compounding to more than they waste through their nonoptimal schedule.​
Well, we can solve it with just one word: FutureFlow.​

FutureFlow is an intelligent energy-management system that schedules your day based on your actual biological capacity, not just empty calendar slots. It uses smart schedualing to improve your productivity and get you into the flow state more often. ​

## Easy to use
The app is divided into tabs which let you organize your task management. Everything you need focus on calender tab and tasks creations. While you add new task you can specity important parameters which affect to task prioritize and required focus span to complete the task. How you use this inputs depends from you. It is possible to fill gaps by hand but also using AI LLM model which based on description and your history assign right values of critical parameters such as needed focus and required time to finish task.

Next, the list of tasks is analized by dedicated algorythm and distributed in time in your schedule. Algorythm is based on statistical REMA curve and in future will be updated using user polling. It takes into account user defined tags representing constant activities during the week time like sleeping or eating dinner. You can define your own tags that will allow you to specify the time ranges in which your tasks should be distributed.

## Our goal and what we have achieved
Our goal is to develop a desktop application designed to help users plan their daily routines, achieve work-life balance, and prioritize healthy meals and physical activity.
We have designed the visual interface and developed a functional prototype featuring core tools and a productivity curve-based planning algorithm.

## How to run
You can download compiled version of app from release page in github and run FutureFlow.exe. Opening app can take some seconds.

Or you can open code using local interpreter configured like shown below:

From PowerShell in the project folder:

```powershell
py -3.14 -m pip install -r requirements.txt
py -3.14 main.py
```



This project expects Python 3.14 with Tkinter support.
